import ast
from datetime import date, datetime
from typing import Any

from fastapi.concurrency import run_in_threadpool
from kubernetes.client import ApiException

from app.kubernetes.client import get_batch_v1_api, get_core_v1_api, get_storage_v1_api
from app.kubernetes.service import list_events


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _container_statuses(pod: Any) -> list[dict[str, Any]]:
    statuses = []
    for status in pod.status.container_statuses or []:
        state = status.state
        last_state = status.last_state
        statuses.append(
            {
                "name": status.name,
                "ready": status.ready,
                "restartCount": status.restart_count or 0,
                "image": status.image,
                "state": _json_safe(state.to_dict()) if state else None,
                "lastState": _json_safe(last_state.to_dict()) if last_state else None,
            }
        )
    return statuses


def _container_specs(pod: Any) -> list[dict[str, Any]]:
    specs = []
    for container in pod.spec.containers or []:
        specs.append(
            {
                "name": container.name,
                "image": container.image,
                "command": container.command or [],
                "args": container.args or [],
                "readinessProbe": _json_safe(container.readiness_probe.to_dict())
                if container.readiness_probe
                else None,
                "livenessProbe": _json_safe(container.liveness_probe.to_dict())
                if container.liveness_probe
                else None,
                "startupProbe": _json_safe(container.startup_probe.to_dict())
                if container.startup_probe
                else None,
                "resources": _json_safe(container.resources.to_dict())
                if container.resources
                else None,
            }
        )
    return specs


def _tool_result(name: str, status: str, params: dict[str, Any], result: Any) -> dict[str, Any]:
    return {"tool": name, "status": status, "params": params, "result": result}


def _normalize_log_text(logs: Any) -> str:
    if isinstance(logs, bytes):
        return logs.decode("utf-8", errors="replace")
    if isinstance(logs, str) and logs.startswith(("b'", 'b"')):
        try:
            parsed = ast.literal_eval(logs)
        except (SyntaxError, ValueError):
            return logs
        if isinstance(parsed, bytes):
            return parsed.decode("utf-8", errors="replace")
    return str(logs)


async def get_pod_details(namespace: str, pod_name: str) -> dict[str, Any]:
    api = get_core_v1_api()
    params = {"namespace": namespace, "pod": pod_name}
    try:
        pod = await run_in_threadpool(api.read_namespaced_pod, pod_name, namespace)
    except ApiException as exc:
        return _tool_result("get_pod_details", "error", params, {"status": exc.status, "reason": exc.reason})

    return _tool_result(
        "get_pod_details",
        "ok",
        params,
        {
            "phase": pod.status.phase,
            "nodeName": pod.spec.node_name,
            "conditions": [_json_safe(condition.to_dict()) for condition in pod.status.conditions or []],
            "containers": _container_statuses(pod),
            "containerSpecs": _container_specs(pod),
        },
    )


async def get_pod_logs(
    namespace: str, pod_name: str, container: str | None = None, tail_lines: int = 50
) -> dict[str, Any]:
    api = get_core_v1_api()
    params = {
        "namespace": namespace,
        "pod": pod_name,
        "container": container,
        "tailLines": tail_lines,
    }
    try:
        logs = await run_in_threadpool(
            api.read_namespaced_pod_log,
            pod_name,
            namespace,
            container=container,
            tail_lines=tail_lines,
            previous=False,
        )
    except ApiException as exc:
        try:
            logs = await run_in_threadpool(
                api.read_namespaced_pod_log,
                pod_name,
                namespace,
                container=container,
                tail_lines=tail_lines,
                previous=True,
            )
        except ApiException as previous_exc:
            return _tool_result(
                "get_pod_logs",
                "error",
                params,
                {"status": previous_exc.status, "reason": previous_exc.reason or exc.reason},
            )

    return _tool_result("get_pod_logs", "ok", params, _normalize_log_text(logs)[-4000:])


async def get_namespace_events(namespace: str) -> dict[str, Any]:
    params = {"namespace": namespace, "limit": 20, "minutes": 60}
    events = await list_events(namespace=namespace, limit=20, minutes=60)
    return _tool_result("get_namespace_events", "ok", params, events)


async def get_pvc_details(namespace: str, pvc_name: str) -> dict[str, Any]:
    api = get_core_v1_api()
    params = {"namespace": namespace, "pvc": pvc_name}
    try:
        pvc = await run_in_threadpool(api.read_namespaced_persistent_volume_claim, pvc_name, namespace)
    except ApiException as exc:
        return _tool_result("get_pvc_details", "error", params, {"status": exc.status, "reason": exc.reason})

    return _tool_result(
        "get_pvc_details",
        "ok",
        params,
        {
            "phase": pvc.status.phase,
            "volumeName": pvc.spec.volume_name,
            "storageClassName": pvc.spec.storage_class_name,
            "accessModes": pvc.spec.access_modes or [],
            "requestedStorage": (pvc.spec.resources.requests or {}).get("storage")
            if pvc.spec.resources
            else None,
        },
    )


async def list_storage_classes() -> dict[str, Any]:
    api = get_storage_v1_api()
    params: dict[str, Any] = {}
    try:
        response = await run_in_threadpool(api.list_storage_class)
    except ApiException as exc:
        return _tool_result("list_storage_classes", "error", params, {"status": exc.status, "reason": exc.reason})

    return _tool_result(
        "list_storage_classes",
        "ok",
        params,
        [
            {
                "name": item.metadata.name,
                "provisioner": item.provisioner,
                "volumeBindingMode": item.volume_binding_mode,
            }
            for item in response.items
        ],
    )


async def get_service_endpoints(namespace: str, service_name: str) -> dict[str, Any]:
    api = get_core_v1_api()
    params = {"namespace": namespace, "service": service_name}
    try:
        service = await run_in_threadpool(api.read_namespaced_service, service_name, namespace)
        endpoints = await run_in_threadpool(api.read_namespaced_endpoints, service_name, namespace)
    except ApiException as exc:
        return _tool_result(
            "get_service_endpoints", "error", params, {"status": exc.status, "reason": exc.reason}
        )

    subsets = endpoints.subsets or []
    return _tool_result(
        "get_service_endpoints",
        "ok",
        params,
        {
            "selector": service.spec.selector or {},
            "ports": [_json_safe(port.to_dict()) for port in service.spec.ports or []],
            "readyAddresses": sum(len(subset.addresses or []) for subset in subsets),
            "notReadyAddresses": sum(len(subset.not_ready_addresses or []) for subset in subsets),
        },
    )


async def get_job_details(namespace: str, job_name: str) -> dict[str, Any]:
    api = get_batch_v1_api()
    params = {"namespace": namespace, "job": job_name}
    try:
        job = await run_in_threadpool(api.read_namespaced_job, job_name, namespace)
    except ApiException as exc:
        return _tool_result("get_job_details", "error", params, {"status": exc.status, "reason": exc.reason})

    return _tool_result(
        "get_job_details",
        "ok",
        params,
        {
            "failed": job.status.failed or 0,
            "succeeded": job.status.succeeded or 0,
            "active": job.status.active or 0,
            "conditions": [_json_safe(condition.to_dict()) for condition in job.status.conditions or []],
            "backoffLimit": job.spec.backoff_limit,
        },
    )


async def run_diagnostic_tools(
    snapshot: dict[str, Any], namespace: str | None = None, max_tools: int = 8, log_tail_lines: int = 50
) -> list[dict[str, Any]]:
    if not namespace:
        return []

    results: list[dict[str, Any]] = []
    findings = snapshot.get("findings", [])
    pods = {pod["name"]: pod for pod in snapshot.get("resources", {}).get("pods", [])}
    seen_resources: set[tuple[Any, Any]] = set()

    async def append(result: dict[str, Any]) -> None:
        if len(results) < max_tools:
            results.append(result)

    await append(await get_namespace_events(namespace))

    unique_findings = []
    for finding in findings:
        resource_key = (finding.get("resourceKind"), finding.get("resourceName"))
        if resource_key in seen_resources:
            continue
        seen_resources.add(resource_key)
        unique_findings.append(finding)

    for kind in ("PersistentVolumeClaim", "Service", "Job"):
        for finding in unique_findings:
            if len(results) >= max_tools:
                break
            name = finding.get("resourceName")
            if finding.get("resourceKind") != kind or not isinstance(name, str):
                continue
            if kind == "PersistentVolumeClaim":
                await append(await get_pvc_details(namespace, name))
                await append(await list_storage_classes())
            elif kind == "Service":
                await append(await get_service_endpoints(namespace, name))
            elif kind == "Job":
                await append(await get_job_details(namespace, name))

    for finding in unique_findings:
        if len(results) >= max_tools:
            break
        name = finding.get("resourceName")
        if finding.get("resourceKind") != "Pod" or not isinstance(name, str) or name not in pods:
            continue
        await append(await get_pod_details(namespace, name))
        container = (pods.get(name, {}).get("containers") or [{}])[0].get("name")
        await append(
            await get_pod_logs(namespace, name, container if isinstance(container, str) else None, log_tail_lines)
        )

    for pod in pods.values():
        if len(results) >= max_tools:
            break
        name = pod.get("name")
        if not isinstance(name, str) or ("Pod", name) in seen_resources:
            continue
        if pod.get("ready") and not pod.get("waitingReason") and int(pod.get("restarts") or 0) == 0:
            continue
        await append(await get_pod_details(namespace, name))
        container = (pod.get("containers") or [{}])[0].get("name")
        await append(
            await get_pod_logs(namespace, name, container if isinstance(container, str) else None, log_tail_lines)
        )

    return results
