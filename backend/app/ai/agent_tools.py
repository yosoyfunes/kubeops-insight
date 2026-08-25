from typing import Any

from app.ai.tools import get_pod_details, get_pod_logs
from app.kubernetes import service as kubernetes_service
from app.metrics.provider import get_metrics_summary

try:
    from strands import tool
except ImportError:  # pragma: no cover - only used before dependencies are installed.
    def tool(func: Any | None = None, *args: Any, **kwargs: Any):
        def decorator(inner: Any) -> Any:
            return inner

        return decorator(func) if callable(func) else decorator


def _limit_items(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return items[: max(0, limit)]


def _compact_pod(pod: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": pod.get("name"),
        "namespace": pod.get("namespace"),
        "phase": pod.get("phase"),
        "ready": pod.get("ready"),
        "restarts": pod.get("restarts"),
        "waitingReason": pod.get("waitingReason"),
        "containers": pod.get("containers", []),
    }


def _matches_hint(value: str | None, hint: str | None) -> bool:
    if not hint:
        return True
    return bool(value and hint.lower() in value.lower())


class KubernetesAgentTools:
    def __init__(self, max_items: int, log_max_lines: int, log_max_characters: int) -> None:
        self.max_items = max_items
        self.log_max_lines = log_max_lines
        self.log_max_characters = log_max_characters

    @tool
    async def get_cluster_summary(self) -> dict[str, Any]:
        """Get a compact live Kubernetes cluster health summary."""
        return await kubernetes_service.get_cluster_summary()

    @tool
    async def get_pods(self, namespace: str | None = None, name_hint: str | None = None) -> list[dict[str, Any]]:
        """List compact pod status, optionally filtered by namespace and name hint.

        Args:
            namespace: Kubernetes namespace to inspect.
            name_hint: Pod name or partial workload name to match.
        """
        pods = await kubernetes_service.list_pods(namespace)
        filtered = [pod for pod in pods if _matches_hint(str(pod.get("name")), name_hint)]
        return [_compact_pod(pod) for pod in _limit_items(filtered, self.max_items)]

    @tool
    async def get_deployment(self, namespace: str, name: str) -> dict[str, Any]:
        """Get one deployment by namespace and name.

        Args:
            namespace: Kubernetes namespace.
            name: Deployment name.
        """
        deployments = await kubernetes_service.list_deployments(namespace)
        for deployment in deployments:
            if deployment.get("name") == name:
                return deployment
        return {"status": "not_found", "namespace": namespace, "name": name}

    @tool
    async def get_events(
        self,
        namespace: str | None = None,
        name_hint: str | None = None,
        limit: int = 20,
        minutes: int = 60,
    ) -> list[dict[str, Any]]:
        """Get recent Kubernetes events, optionally filtered by namespace and object name hint.

        Args:
            namespace: Kubernetes namespace.
            name_hint: Involved object name hint.
            limit: Maximum events to return.
            minutes: Time window in minutes.
        """
        events = await kubernetes_service.list_events(namespace, min(limit, self.max_items), minutes)
        if name_hint:
            events = [
                event
                for event in events
                if _matches_hint(str((event.get("involvedObject") or {}).get("name")), name_hint)
                or _matches_hint(str(event.get("message")), name_hint)
            ]
        return _limit_items(events, min(limit, self.max_items))

    @tool
    async def get_logs(
        self,
        namespace: str,
        pod_name: str,
        container: str | None = None,
    ) -> dict[str, Any]:
        """Get bounded current or previous logs for a pod container.

        Args:
            namespace: Kubernetes namespace.
            pod_name: Pod name.
            container: Optional container name.
        """
        result = await get_pod_logs(namespace, pod_name, container, self.log_max_lines)
        if result.get("status") != "ok" or not isinstance(result.get("result"), str):
            return result
        lines = result["result"].splitlines()[-self.log_max_lines :]
        truncated = "\n".join(lines)[-self.log_max_characters :]
        return {**result, "result": truncated}

    @tool
    async def get_pod_details(self, namespace: str, pod_name: str) -> dict[str, Any]:
        """Get container states, last termination state and conditions for one pod.

        Args:
            namespace: Kubernetes namespace.
            pod_name: Pod name.
        """
        return await get_pod_details(namespace, pod_name)

    @tool
    async def get_metrics(self) -> dict[str, Any]:
        """Get compact Metrics Server summary when available."""
        return await get_metrics_summary()

    @tool
    async def find_unhealthy_workloads(
        self, namespace: str | None = None, name_hint: str | None = None
    ) -> dict[str, Any]:
        """Find unhealthy pods, deployments, PVCs and deterministic findings.

        Args:
            namespace: Kubernetes namespace to inspect.
            name_hint: Optional workload, pod or resource name hint from the user's question.
        """
        findings = await kubernetes_service.get_findings()
        pods = await kubernetes_service.list_pods(namespace)
        deployments = await kubernetes_service.list_deployments(namespace)
        pvcs = await kubernetes_service.list_pvcs(namespace)

        if namespace:
            findings = [finding for finding in findings if finding.get("namespace") == namespace]
        if name_hint:
            findings = [
                finding
                for finding in findings
                if _matches_hint(str(finding.get("resourceName")), name_hint)
                or _matches_hint(str(finding.get("summary")), name_hint)
            ]

        unhealthy_pods = [
            pod
            for pod in pods
            if (not pod.get("ready")) or pod.get("waitingReason") or int(pod.get("restarts") or 0) > 0
        ]
        if name_hint:
            unhealthy_pods = [pod for pod in unhealthy_pods if _matches_hint(str(pod.get("name")), name_hint)]

        unhealthy_deployments = [deployment for deployment in deployments if not deployment.get("available")]
        if name_hint:
            unhealthy_deployments = [
                deployment
                for deployment in unhealthy_deployments
                if _matches_hint(str(deployment.get("name")), name_hint)
            ]

        pending_pvcs = [pvc for pvc in pvcs if pvc.get("phase") == "Pending"]
        return {
            "findings": _limit_items(findings, self.max_items),
            "pods": [_compact_pod(pod) for pod in _limit_items(unhealthy_pods, self.max_items)],
            "deployments": _limit_items(unhealthy_deployments, self.max_items),
            "pvcs": _limit_items(pending_pvcs, self.max_items),
        }
