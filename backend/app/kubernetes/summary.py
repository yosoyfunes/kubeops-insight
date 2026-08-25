from datetime import UTC, datetime
from typing import Any

from kubernetes import client


def _condition_status(conditions: list[Any] | None, condition_type: str) -> str | None:
    for condition in conditions or []:
        if condition.type == condition_type:
            return condition.status
    return None


def _pod_waiting_reason(pod: client.V1Pod) -> str | None:
    for container_status in pod.status.container_statuses or []:
        waiting = container_status.state.waiting if container_status.state else None
        if waiting and waiting.reason:
            return waiting.reason
    return None


def _pod_restarts(pod: client.V1Pod) -> int:
    return sum(status.restart_count or 0 for status in pod.status.container_statuses or [])


def summarize_cluster(
    nodes: list[client.V1Node],
    namespaces: list[client.V1Namespace],
    pods: list[client.V1Pod],
    deployments: list[client.V1Deployment],
    events: list[client.CoreV1Event],
) -> dict[str, Any]:
    ready_nodes = sum(1 for node in nodes if _condition_status(node.status.conditions, "Ready") == "True")
    warning_events = [event for event in events if event.type == "Warning"]
    crash_loop_pods = [pod for pod in pods if _pod_waiting_reason(pod) == "CrashLoopBackOff"]
    high_restart_pods = [pod for pod in pods if _pod_restarts(pod) >= 5]
    unavailable_deployments = [
        deployment
        for deployment in deployments
        if (deployment.status.available_replicas or 0) < (deployment.spec.replicas or 0)
    ]

    return {
        "mode": "live",
        "timestamp": datetime.now(UTC).isoformat(),
        "cluster": {
            "status": "healthy" if ready_nodes == len(nodes) and not crash_loop_pods else "degraded",
            "nodes": len(nodes),
            "readyNodes": ready_nodes,
            "notReadyNodes": len(nodes) - ready_nodes,
            "namespaces": len(namespaces),
            "pods": {
                "running": sum(1 for pod in pods if pod.status.phase == "Running"),
                "pending": sum(1 for pod in pods if pod.status.phase == "Pending"),
                "failed": sum(1 for pod in pods if pod.status.phase == "Failed"),
                "crashLoopBackOff": len(crash_loop_pods),
                "highRestarts": len(high_restart_pods),
            },
            "deployments": {
                "available": len(deployments) - len(unavailable_deployments),
                "unavailable": len(unavailable_deployments),
            },
            "events": {"warningsLastHour": len(warning_events)},
        },
        "metrics": {
            "provider": "kubernetes-api",
            "cpuUsageCores": None,
            "memoryUsageGiB": None,
        },
        "source": "kubernetes-api",
    }
