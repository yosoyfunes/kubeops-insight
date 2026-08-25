from typing import Any

from fastapi.concurrency import run_in_threadpool
from kubernetes.client import ApiException

from app.kubernetes.client import get_custom_objects_api


def _parse_cpu_to_millicores(value: str) -> float:
    if value.endswith("n"):
        return float(value[:-1]) / 1_000_000
    if value.endswith("u"):
        return float(value[:-1]) / 1_000
    if value.endswith("m"):
        return float(value[:-1])
    return float(value) * 1000


def _parse_memory_to_mib(value: str) -> float:
    units = {
        "Ki": 1 / 1024,
        "Mi": 1,
        "Gi": 1024,
        "Ti": 1024 * 1024,
    }
    for suffix, multiplier in units.items():
        if value.endswith(suffix):
            return float(value[: -len(suffix)]) * multiplier
    return float(value) / (1024 * 1024)


def _pod_usage(pod_metric: dict[str, Any]) -> dict[str, Any]:
    cpu_millicores = 0.0
    memory_mib = 0.0
    for container in pod_metric.get("containers", []):
        usage = container.get("usage", {})
        cpu_millicores += _parse_cpu_to_millicores(usage.get("cpu", "0"))
        memory_mib += _parse_memory_to_mib(usage.get("memory", "0"))

    return {
        "name": pod_metric["metadata"]["name"],
        "namespace": pod_metric["metadata"]["namespace"],
        "cpuMillicores": round(cpu_millicores, 2),
        "memoryMiB": round(memory_mib, 2),
    }


async def get_metrics_summary() -> dict[str, Any]:
    api = get_custom_objects_api()
    try:
        node_metrics = await run_in_threadpool(
            api.list_cluster_custom_object,
            "metrics.k8s.io",
            "v1beta1",
            "nodes",
        )
        pod_metrics = await run_in_threadpool(
            api.list_cluster_custom_object,
            "metrics.k8s.io",
            "v1beta1",
            "pods",
        )
    except ApiException as exc:
        if exc.status == 404:
            return {
                "provider": "metrics-server",
                "status": "unavailable",
                "reason": "Metrics API is not available in this cluster.",
            }
        raise

    pods = [_pod_usage(item) for item in pod_metrics.get("items", [])]
    top_cpu = sorted(pods, key=lambda pod: pod["cpuMillicores"], reverse=True)[:5]
    top_memory = sorted(pods, key=lambda pod: pod["memoryMiB"], reverse=True)[:5]

    return {
        "provider": "metrics-server",
        "status": "available",
        "nodes": len(node_metrics.get("items", [])),
        "pods": len(pods),
        "topCpuPods": top_cpu,
        "topMemoryPods": top_memory,
    }
