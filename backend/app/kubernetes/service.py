from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.concurrency import run_in_threadpool
from kubernetes import client

from app.diagnostics.rules import find_issues
from app.kubernetes.client import (
    get_apps_v1_api,
    get_batch_v1_api,
    get_core_v1_api,
    get_networking_v1_api,
)
from app.kubernetes.store import cluster_state_store
from app.kubernetes.summary import summarize_cluster


def _metadata(resource: Any) -> dict[str, str | None]:
    return {
        "name": resource.metadata.name,
        "namespace": resource.metadata.namespace,
        "creationTimestamp": resource.metadata.creation_timestamp.isoformat()
        if resource.metadata.creation_timestamp
        else None,
    }


def _node_to_dict(node: client.V1Node) -> dict[str, Any]:
    ready = next(
        (condition.status for condition in node.status.conditions or [] if condition.type == "Ready"),
        "Unknown",
    )
    return {
        **_metadata(node),
        "ready": ready == "True",
        "conditions": [
            {"type": condition.type, "status": condition.status, "reason": condition.reason}
            for condition in node.status.conditions or []
        ],
    }


def _pod_to_dict(pod: client.V1Pod) -> dict[str, Any]:
    container_statuses = pod.status.container_statuses or []
    waiting_reasons = [
        status.state.waiting.reason
        for status in container_statuses
        if status.state and status.state.waiting and status.state.waiting.reason
    ]
    ready_containers = sum(1 for status in container_statuses if status.ready)
    return {
        **_metadata(pod),
        "phase": pod.status.phase,
        "nodeName": pod.spec.node_name,
        "ready": ready_containers == len(container_statuses) if container_statuses else False,
        "readyContainers": ready_containers,
        "totalContainers": len(container_statuses),
        "restarts": sum(status.restart_count or 0 for status in container_statuses),
        "waitingReason": waiting_reasons[0] if waiting_reasons else None,
        "containers": [
            {
                "name": status.name,
                "ready": status.ready,
                "restarts": status.restart_count or 0,
                "image": status.image,
            }
            for status in container_statuses
        ],
    }


def _deployment_to_dict(deployment: client.V1Deployment) -> dict[str, Any]:
    desired = deployment.spec.replicas or 0
    available = deployment.status.available_replicas or 0
    return {
        **_metadata(deployment),
        "desiredReplicas": desired,
        "availableReplicas": available,
        "readyReplicas": deployment.status.ready_replicas or 0,
        "updatedReplicas": deployment.status.updated_replicas or 0,
        "available": available >= desired,
    }


def _statefulset_to_dict(statefulset: client.V1StatefulSet) -> dict[str, Any]:
    desired = statefulset.spec.replicas or 0
    ready = statefulset.status.ready_replicas or 0
    return {
        **_metadata(statefulset),
        "desiredReplicas": desired,
        "readyReplicas": ready,
        "available": ready >= desired,
    }


def _daemonset_to_dict(daemonset: client.V1DaemonSet) -> dict[str, Any]:
    desired = daemonset.status.desired_number_scheduled or 0
    ready = daemonset.status.number_ready or 0
    return {
        **_metadata(daemonset),
        "desiredNumberScheduled": desired,
        "numberReady": ready,
        "available": ready >= desired,
    }


def _job_to_dict(job: client.V1Job) -> dict[str, Any]:
    failed = job.status.failed or 0
    succeeded = job.status.succeeded or 0
    completions = job.spec.completions or 1
    return {
        **_metadata(job),
        "failed": failed,
        "succeeded": succeeded,
        "completions": completions,
        "complete": succeeded >= completions,
    }


def _service_to_dict(service: client.V1Service) -> dict[str, Any]:
    return {
        **_metadata(service),
        "type": service.spec.type,
        "clusterIP": service.spec.cluster_ip,
        "externalIPs": service.spec.external_ips or [],
        "ports": [
            {"name": port.name, "port": port.port, "targetPort": str(port.target_port)}
            for port in service.spec.ports or []
        ],
    }


def _pvc_to_dict(pvc: client.V1PersistentVolumeClaim) -> dict[str, Any]:
    return {
        **_metadata(pvc),
        "phase": pvc.status.phase,
        "volumeName": pvc.spec.volume_name,
        "storageClassName": pvc.spec.storage_class_name,
    }


def _ingress_to_dict(ingress: client.V1Ingress) -> dict[str, Any]:
    rules = ingress.spec.rules or []
    return {
        **_metadata(ingress),
        "className": ingress.spec.ingress_class_name,
        "hosts": [rule.host for rule in rules if rule.host],
    }


def _event_to_dict(event: client.CoreV1Event) -> dict[str, Any]:
    return {
        **_metadata(event),
        "type": event.type,
        "reason": event.reason,
        "message": event.message,
        "involvedObject": {
            "kind": event.involved_object.kind,
            "name": event.involved_object.name,
            "namespace": event.involved_object.namespace,
        }
        if event.involved_object
        else None,
        "lastTimestamp": event.last_timestamp.isoformat() if event.last_timestamp else None,
    }


def _event_time(event: client.CoreV1Event) -> datetime | None:
    return event.last_timestamp or event.event_time or event.first_timestamp


def _filter_recent_events(
    events: list[client.CoreV1Event], minutes: int = 60, limit: int = 50
) -> list[client.CoreV1Event]:
    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    recent = [event for event in events if (event_time := _event_time(event)) and event_time >= cutoff]
    return sorted(recent, key=lambda event: _event_time(event) or datetime.min.replace(tzinfo=UTC))[
        -limit:
    ]


async def list_namespaces() -> list[dict[str, Any]]:
    return await cluster_state_store.get("namespaces", _list_namespaces_uncached)


async def _list_namespaces_uncached() -> list[dict[str, Any]]:
    api = get_core_v1_api()
    response = await run_in_threadpool(api.list_namespace)
    return [_metadata(namespace) for namespace in response.items]


async def list_nodes() -> list[dict[str, Any]]:
    return await cluster_state_store.get("nodes", _list_nodes_uncached)


async def _list_nodes_uncached() -> list[dict[str, Any]]:
    api = get_core_v1_api()
    response = await run_in_threadpool(api.list_node)
    return [_node_to_dict(node) for node in response.items]


async def list_pods(namespace: str | None = None) -> list[dict[str, Any]]:
    return await cluster_state_store.get(f"pods:{namespace or 'all'}", lambda: _list_pods_uncached(namespace))


async def _list_pods_uncached(namespace: str | None = None) -> list[dict[str, Any]]:
    api = get_core_v1_api()
    if namespace:
        response = await run_in_threadpool(api.list_namespaced_pod, namespace)
    else:
        response = await run_in_threadpool(api.list_pod_for_all_namespaces)
    return [_pod_to_dict(pod) for pod in response.items]


async def get_pod(namespace: str, name: str) -> dict[str, Any]:
    api = get_core_v1_api()
    pod = await run_in_threadpool(api.read_namespaced_pod, name, namespace)
    return _pod_to_dict(pod)


async def list_deployments(namespace: str | None = None) -> list[dict[str, Any]]:
    return await cluster_state_store.get(
        f"deployments:{namespace or 'all'}", lambda: _list_deployments_uncached(namespace)
    )


async def _list_deployments_uncached(namespace: str | None = None) -> list[dict[str, Any]]:
    api = get_apps_v1_api()
    if namespace:
        response = await run_in_threadpool(api.list_namespaced_deployment, namespace)
    else:
        response = await run_in_threadpool(api.list_deployment_for_all_namespaces)
    return [_deployment_to_dict(deployment) for deployment in response.items]


async def list_services(namespace: str | None = None) -> list[dict[str, Any]]:
    return await cluster_state_store.get(
        f"services:{namespace or 'all'}", lambda: _list_services_uncached(namespace)
    )


async def _list_services_uncached(namespace: str | None = None) -> list[dict[str, Any]]:
    api = get_core_v1_api()
    if namespace:
        response = await run_in_threadpool(api.list_namespaced_service, namespace)
    else:
        response = await run_in_threadpool(api.list_service_for_all_namespaces)
    return [_service_to_dict(service) for service in response.items]


async def list_events(
    namespace: str | None = None, limit: int = 50, minutes: int = 60
) -> list[dict[str, Any]]:
    return await cluster_state_store.get(
        f"events:{namespace or 'all'}:{limit}:{minutes}",
        lambda: _list_events_uncached(namespace, limit, minutes),
    )


async def _list_events_uncached(
    namespace: str | None = None, limit: int = 50, minutes: int = 60
) -> list[dict[str, Any]]:
    api = get_core_v1_api()
    if namespace:
        response = await run_in_threadpool(api.list_namespaced_event, namespace)
    else:
        response = await run_in_threadpool(api.list_event_for_all_namespaces)
    return [_event_to_dict(event) for event in _filter_recent_events(response.items, minutes, limit)]


async def get_namespace_summary(namespace: str) -> dict[str, Any]:
    return await cluster_state_store.get(
        f"namespace-summary:{namespace}", lambda: _get_namespace_summary_uncached(namespace)
    )


async def _get_namespace_summary_uncached(namespace: str) -> dict[str, Any]:
    core_api = get_core_v1_api()
    apps_api = get_apps_v1_api()

    pods = await run_in_threadpool(core_api.list_namespaced_pod, namespace)
    deployments = await run_in_threadpool(apps_api.list_namespaced_deployment, namespace)
    services = await run_in_threadpool(core_api.list_namespaced_service, namespace)
    events = await run_in_threadpool(core_api.list_namespaced_event, namespace)

    unavailable_deployments = [
        deployment
        for deployment in deployments.items
        if (deployment.status.available_replicas or 0) < (deployment.spec.replicas or 0)
    ]
    recent_warning_events = [
        event for event in _filter_recent_events(events.items) if event.type == "Warning"
    ]

    return {
        "namespace": namespace,
        "pods": {
            "total": len(pods.items),
            "running": sum(1 for pod in pods.items if pod.status.phase == "Running"),
            "pending": sum(1 for pod in pods.items if pod.status.phase == "Pending"),
            "failed": sum(1 for pod in pods.items if pod.status.phase == "Failed"),
        },
        "deployments": {
            "total": len(deployments.items),
            "unavailable": len(unavailable_deployments),
        },
        "services": {"total": len(services.items)},
        "events": {"warningRecent": len(recent_warning_events)},
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def get_workloads(namespace: str | None = None) -> dict[str, Any]:
    return await cluster_state_store.get(
        f"workloads:{namespace or 'all'}", lambda: _get_workloads_uncached(namespace)
    )


async def _get_workloads_uncached(namespace: str | None = None) -> dict[str, Any]:
    api = get_apps_v1_api()

    if namespace:
        deployments = await run_in_threadpool(api.list_namespaced_deployment, namespace)
        statefulsets = await run_in_threadpool(api.list_namespaced_stateful_set, namespace)
        daemonsets = await run_in_threadpool(api.list_namespaced_daemon_set, namespace)
    else:
        deployments = await run_in_threadpool(api.list_deployment_for_all_namespaces)
        statefulsets = await run_in_threadpool(api.list_stateful_set_for_all_namespaces)
        daemonsets = await run_in_threadpool(api.list_daemon_set_for_all_namespaces)

    return {
        "deployments": [_deployment_to_dict(deployment) for deployment in deployments.items],
        "statefulSets": [_statefulset_to_dict(statefulset) for statefulset in statefulsets.items],
        "daemonSets": [_daemonset_to_dict(daemonset) for daemonset in daemonsets.items],
    }


async def list_statefulsets(namespace: str | None = None) -> list[dict[str, Any]]:
    return (await get_workloads(namespace))["statefulSets"]


async def list_daemonsets(namespace: str | None = None) -> list[dict[str, Any]]:
    return (await get_workloads(namespace))["daemonSets"]


async def list_jobs(namespace: str | None = None) -> list[dict[str, Any]]:
    return await cluster_state_store.get(f"jobs:{namespace or 'all'}", lambda: _list_jobs_uncached(namespace))


async def _list_jobs_uncached(namespace: str | None = None) -> list[dict[str, Any]]:
    api = get_batch_v1_api()
    if namespace:
        response = await run_in_threadpool(api.list_namespaced_job, namespace)
    else:
        response = await run_in_threadpool(api.list_job_for_all_namespaces)
    return [_job_to_dict(job) for job in response.items]


async def list_ingresses(namespace: str | None = None) -> list[dict[str, Any]]:
    return await cluster_state_store.get(
        f"ingresses:{namespace or 'all'}", lambda: _list_ingresses_uncached(namespace)
    )


async def _list_ingresses_uncached(namespace: str | None = None) -> list[dict[str, Any]]:
    api = get_networking_v1_api()
    if namespace:
        response = await run_in_threadpool(api.list_namespaced_ingress, namespace)
    else:
        response = await run_in_threadpool(api.list_ingress_for_all_namespaces)
    return [_ingress_to_dict(ingress) for ingress in response.items]


async def get_cluster_summary() -> dict[str, Any]:
    return await cluster_state_store.get("cluster-summary", _get_cluster_summary_uncached)


async def _get_cluster_summary_uncached() -> dict[str, Any]:
    core_api = get_core_v1_api()
    apps_api = get_apps_v1_api()

    nodes = await run_in_threadpool(core_api.list_node)
    namespaces = await run_in_threadpool(core_api.list_namespace)
    pods = await run_in_threadpool(core_api.list_pod_for_all_namespaces)
    deployments = await run_in_threadpool(apps_api.list_deployment_for_all_namespaces)
    events = await run_in_threadpool(core_api.list_event_for_all_namespaces)

    return summarize_cluster(
        nodes.items,
        namespaces.items,
        pods.items,
        deployments.items,
        _filter_recent_events(events.items),
    )


async def get_findings() -> list[dict[str, Any]]:
    return await cluster_state_store.get("findings", _get_findings_uncached)


async def _get_findings_uncached() -> list[dict[str, Any]]:
    core_api = get_core_v1_api()
    apps_api = get_apps_v1_api()

    nodes = await run_in_threadpool(core_api.list_node)
    pods = await run_in_threadpool(core_api.list_pod_for_all_namespaces)
    deployments = await run_in_threadpool(apps_api.list_deployment_for_all_namespaces)
    events = await run_in_threadpool(core_api.list_event_for_all_namespaces)
    pvcs = await run_in_threadpool(core_api.list_persistent_volume_claim_for_all_namespaces)
    services = await run_in_threadpool(core_api.list_service_for_all_namespaces)
    endpoints = await run_in_threadpool(core_api.list_endpoints_for_all_namespaces)
    statefulsets = await run_in_threadpool(apps_api.list_stateful_set_for_all_namespaces)
    daemonsets = await run_in_threadpool(apps_api.list_daemon_set_for_all_namespaces)
    jobs = await run_in_threadpool(get_batch_v1_api().list_job_for_all_namespaces)

    return find_issues(
        nodes.items,
        pods.items,
        deployments.items,
        _filter_recent_events(events.items),
        pvcs.items,
        services.items,
        endpoints.items,
        statefulsets.items,
        daemonsets.items,
        jobs.items,
    )


async def list_pvcs(namespace: str | None = None) -> list[dict[str, Any]]:
    return await cluster_state_store.get(f"pvcs:{namespace or 'all'}", lambda: _list_pvcs_uncached(namespace))


async def _list_pvcs_uncached(namespace: str | None = None) -> list[dict[str, Any]]:
    api = get_core_v1_api()
    if namespace:
        response = await run_in_threadpool(api.list_namespaced_persistent_volume_claim, namespace)
    else:
        response = await run_in_threadpool(api.list_persistent_volume_claim_for_all_namespaces)
    return [_pvc_to_dict(pvc) for pvc in response.items]
