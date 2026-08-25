from datetime import UTC, datetime
from typing import Any

from kubernetes import client


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _finding(
    finding_id: str,
    severity: str,
    resource_kind: str,
    resource_name: str,
    namespace: str | None,
    summary: str,
    evidence: list[str],
    recommendation: str,
) -> dict[str, Any]:
    return {
        "id": finding_id,
        "severity": severity,
        "resourceKind": resource_kind,
        "resourceName": resource_name,
        "namespace": namespace,
        "summary": summary,
        "evidence": evidence,
        "recommendation": recommendation,
        "timestamp": _timestamp(),
    }


def _waiting_reason(pod: client.V1Pod) -> str | None:
    for container_status in pod.status.container_statuses or []:
        waiting = container_status.state.waiting if container_status.state else None
        if waiting and waiting.reason:
            return waiting.reason
    return None


def _restart_count(pod: client.V1Pod) -> int:
    return sum(status.restart_count or 0 for status in pod.status.container_statuses or [])


def _node_condition(node: client.V1Node, condition_type: str) -> client.V1NodeCondition | None:
    for condition in node.status.conditions or []:
        if condition.type == condition_type:
            return condition
    return None


def find_pod_issues(pods: list[client.V1Pod]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for pod in pods:
        name = pod.metadata.name
        namespace = pod.metadata.namespace
        reason = _waiting_reason(pod)
        restarts = _restart_count(pod)

        if reason == "CrashLoopBackOff":
            findings.append(
                _finding(
                    f"pod-crashloop-{namespace}-{name}",
                    "critical",
                    "Pod",
                    name,
                    namespace,
                    f"Pod {name} is in CrashLoopBackOff.",
                    [f"waitingReason={reason}", f"restartCount={restarts}"],
                    "Inspect container logs, recent events, command arguments and health probes.",
                )
            )

        if reason in {"ImagePullBackOff", "ErrImagePull"}:
            findings.append(
                _finding(
                    f"pod-imagepull-{namespace}-{name}",
                    "warning",
                    "Pod",
                    name,
                    namespace,
                    f"Pod {name} cannot pull its image.",
                    [f"waitingReason={reason}"],
                    "Verify image name, tag, registry availability and image pull secrets.",
                )
            )

        if pod.status.phase == "Pending":
            findings.append(
                _finding(
                    f"pod-pending-{namespace}-{name}",
                    "warning",
                    "Pod",
                    name,
                    namespace,
                    f"Pod {name} is Pending.",
                    [f"phase={pod.status.phase}", f"nodeName={pod.spec.node_name}"],
                    "Check scheduling events, resource requests, taints, tolerations and PVC binding.",
                )
            )

        if pod.status.phase == "Failed":
            findings.append(
                _finding(
                    f"pod-failed-{namespace}-{name}",
                    "critical",
                    "Pod",
                    name,
                    namespace,
                    f"Pod {name} is Failed.",
                    [f"phase={pod.status.phase}", f"reason={pod.status.reason}"],
                    "Inspect pod status, termination reason and controller replacement behavior.",
                )
            )

        if restarts >= 5:
            findings.append(
                _finding(
                    f"pod-high-restarts-{namespace}-{name}",
                    "warning",
                    "Pod",
                    name,
                    namespace,
                    f"Pod {name} has a high restart count.",
                    [f"restartCount={restarts}"],
                    "Inspect logs and probes to identify repeated container failures.",
                )
            )

        for container in pod.spec.containers or []:
            if container.image and container.image.endswith(":latest"):
                findings.append(
                    _finding(
                        f"pod-latest-image-{namespace}-{name}-{container.name}",
                        "info",
                        "Pod",
                        name,
                        namespace,
                        f"Container {container.name} uses the latest image tag.",
                        [f"image={container.image}"],
                        "Use immutable image tags for predictable rollouts.",
                    )
                )
            if not container.resources or not container.resources.requests:
                findings.append(
                    _finding(
                        f"pod-missing-requests-{namespace}-{name}-{container.name}",
                        "info",
                        "Pod",
                        name,
                        namespace,
                        f"Container {container.name} has no resource requests.",
                        ["requests=missing"],
                        "Set CPU and memory requests to improve scheduling and capacity planning.",
                    )
                )
            if not container.resources or not container.resources.limits:
                findings.append(
                    _finding(
                        f"pod-missing-limits-{namespace}-{name}-{container.name}",
                        "info",
                        "Pod",
                        name,
                        namespace,
                        f"Container {container.name} has no resource limits.",
                        ["limits=missing"],
                        "Set CPU and memory limits where appropriate to reduce noisy-neighbor risk.",
                    )
                )

        has_readiness_probe = any(container.readiness_probe for container in pod.spec.containers or [])
        if pod.status.phase == "Running" and not has_readiness_probe:
            findings.append(
                _finding(
                    f"pod-no-readiness-probe-{namespace}-{name}",
                    "info",
                    "Pod",
                    name,
                    namespace,
                    f"Pod {name} has no readiness probe.",
                    ["readinessProbe=missing"],
                    "Add readiness probes for workload traffic safety during startup and rollouts.",
                )
            )

    return findings


def find_deployment_issues(deployments: list[client.V1Deployment]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for deployment in deployments:
        desired = deployment.spec.replicas or 0
        available = deployment.status.available_replicas or 0
        if available < desired:
            findings.append(
                _finding(
                    f"deployment-unavailable-{deployment.metadata.namespace}-{deployment.metadata.name}",
                    "warning",
                    "Deployment",
                    deployment.metadata.name,
                    deployment.metadata.namespace,
                    f"Deployment {deployment.metadata.name} has unavailable replicas.",
                    [f"desiredReplicas={desired}", f"availableReplicas={available}"],
                    "Check rollout status, replica set events and pod readiness failures.",
                )
            )

    return findings


def find_node_issues(nodes: list[client.V1Node]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for node in nodes:
        ready = _node_condition(node, "Ready")
        if not ready or ready.status != "True":
            findings.append(
                _finding(
                    f"node-not-ready-{node.metadata.name}",
                    "critical",
                    "Node",
                    node.metadata.name,
                    None,
                    f"Node {node.metadata.name} is not Ready.",
                    [f"readyStatus={ready.status if ready else 'Unknown'}"],
                    "Check kubelet status, node conditions and cluster infrastructure health.",
                )
            )

        for condition_type in ("MemoryPressure", "DiskPressure", "PIDPressure"):
            condition = _node_condition(node, condition_type)
            if condition and condition.status == "True":
                findings.append(
                    _finding(
                        f"node-pressure-{condition_type.lower()}-{node.metadata.name}",
                        "warning",
                        "Node",
                        node.metadata.name,
                        None,
                        f"Node {node.metadata.name} reports {condition_type}.",
                        [f"condition={condition_type}", f"reason={condition.reason}"],
                        "Inspect node resource pressure and evicted workloads.",
                    )
                )

    return findings


def find_event_issues(events: list[client.CoreV1Event], limit: int = 20) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    warning_events = [event for event in events if event.type == "Warning"][-limit:]
    for event in warning_events:
        involved = event.involved_object
        findings.append(
            _finding(
                f"event-warning-{event.metadata.namespace}-{event.metadata.name}",
                "info",
                involved.kind if involved else "Event",
                involved.name if involved else event.metadata.name,
                event.metadata.namespace,
                event.message or "Warning event observed.",
                [f"reason={event.reason}", f"type={event.type}"],
                "Review the involved resource and surrounding events for context.",
            )
        )

    return findings


def find_pvc_issues(pvcs: list[client.V1PersistentVolumeClaim]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []

    for pvc in pvcs:
        if pvc.status.phase == "Pending":
            findings.append(
                _finding(
                    f"pvc-pending-{pvc.metadata.namespace}-{pvc.metadata.name}",
                    "warning",
                    "PersistentVolumeClaim",
                    pvc.metadata.name,
                    pvc.metadata.namespace,
                    f"PVC {pvc.metadata.name} is Pending.",
                    [
                        f"phase={pvc.status.phase}",
                        f"storageClassName={pvc.spec.storage_class_name}",
                    ],
                    "Check StorageClass availability, provisioner health and requested storage constraints.",
                )
            )

    return findings


def find_service_issues(
    services: list[client.V1Service], endpoints: list[client.V1Endpoints]
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    endpoints_by_key = {
        (endpoint.metadata.namespace, endpoint.metadata.name): endpoint for endpoint in endpoints
    }

    for service in services:
        if service.spec.type == "ExternalName":
            continue

        endpoint = endpoints_by_key.get((service.metadata.namespace, service.metadata.name))
        has_addresses = any(subset.addresses for subset in endpoint.subsets or []) if endpoint else False
        if not has_addresses:
            findings.append(
                _finding(
                    f"service-no-endpoints-{service.metadata.namespace}-{service.metadata.name}",
                    "warning",
                    "Service",
                    service.metadata.name,
                    service.metadata.namespace,
                    f"Service {service.metadata.name} has no ready endpoints.",
                    [f"type={service.spec.type}", f"clusterIP={service.spec.cluster_ip}"],
                    "Check service selector labels and backing pod readiness.",
                )
            )

    return findings


def find_statefulset_issues(statefulsets: list[client.V1StatefulSet]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for statefulset in statefulsets:
        desired = statefulset.spec.replicas or 0
        ready = statefulset.status.ready_replicas or 0
        if ready < desired:
            findings.append(
                _finding(
                    f"statefulset-incomplete-{statefulset.metadata.namespace}-{statefulset.metadata.name}",
                    "warning",
                    "StatefulSet",
                    statefulset.metadata.name,
                    statefulset.metadata.namespace,
                    f"StatefulSet {statefulset.metadata.name} is incomplete.",
                    [f"desiredReplicas={desired}", f"readyReplicas={ready}"],
                    "Check pod readiness, PVC binding and ordered rollout status.",
                )
            )
    return findings


def find_daemonset_issues(daemonsets: list[client.V1DaemonSet]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for daemonset in daemonsets:
        desired = daemonset.status.desired_number_scheduled or 0
        ready = daemonset.status.number_ready or 0
        if ready < desired:
            findings.append(
                _finding(
                    f"daemonset-unhealthy-{daemonset.metadata.namespace}-{daemonset.metadata.name}",
                    "warning",
                    "DaemonSet",
                    daemonset.metadata.name,
                    daemonset.metadata.namespace,
                    f"DaemonSet {daemonset.metadata.name} is not ready on all scheduled nodes.",
                    [f"desiredNumberScheduled={desired}", f"numberReady={ready}"],
                    "Check node selectors, tolerations and daemon pod readiness.",
                )
            )
    return findings


def find_job_issues(jobs: list[client.V1Job]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for job in jobs:
        failed = job.status.failed or 0
        if failed > 0:
            findings.append(
                _finding(
                    f"job-failed-{job.metadata.namespace}-{job.metadata.name}",
                    "warning",
                    "Job",
                    job.metadata.name,
                    job.metadata.namespace,
                    f"Job {job.metadata.name} has failed pods.",
                    [f"failed={failed}", f"succeeded={job.status.succeeded or 0}"],
                    "Inspect job pod logs, backoffLimit and completion status.",
                )
            )
    return findings


def find_issues(
    nodes: list[client.V1Node],
    pods: list[client.V1Pod],
    deployments: list[client.V1Deployment],
    events: list[client.CoreV1Event],
    pvcs: list[client.V1PersistentVolumeClaim] | None = None,
    services: list[client.V1Service] | None = None,
    endpoints: list[client.V1Endpoints] | None = None,
    statefulsets: list[client.V1StatefulSet] | None = None,
    daemonsets: list[client.V1DaemonSet] | None = None,
    jobs: list[client.V1Job] | None = None,
) -> list[dict[str, Any]]:
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    findings = [
        *find_node_issues(nodes),
        *find_deployment_issues(deployments),
        *find_pod_issues(pods),
        *find_pvc_issues(pvcs or []),
        *find_service_issues(services or [], endpoints or []),
        *find_statefulset_issues(statefulsets or []),
        *find_daemonset_issues(daemonsets or []),
        *find_job_issues(jobs or []),
        *find_event_issues(events),
    ]
    return sorted(findings, key=lambda finding: severity_order[finding["severity"]])
