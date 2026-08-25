from kubernetes import client

from app.diagnostics.rules import (
    find_deployment_issues,
    find_node_issues,
    find_pod_issues,
    find_pvc_issues,
    find_service_issues,
)


def test_detects_crash_loop_backoff_pod() -> None:
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name="api", namespace="default"),
        spec=client.V1PodSpec(containers=[client.V1Container(name="api", image="api")]),
        status=client.V1PodStatus(
            phase="Running",
            container_statuses=[
                client.V1ContainerStatus(
                    name="api",
                    image="api",
                    image_id="api",
                    ready=False,
                    restart_count=7,
                    state=client.V1ContainerState(
                        waiting=client.V1ContainerStateWaiting(reason="CrashLoopBackOff")
                    ),
                )
            ],
        ),
    )

    findings = find_pod_issues([pod])

    assert findings[0]["severity"] == "critical"
    assert findings[0]["resourceKind"] == "Pod"
    assert "CrashLoopBackOff" in findings[0]["summary"]


def test_detects_unavailable_deployment() -> None:
    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(name="api", namespace="default"),
        spec=client.V1DeploymentSpec(
            selector=client.V1LabelSelector(match_labels={"app": "api"}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "api"}),
                spec=client.V1PodSpec(containers=[client.V1Container(name="api", image="api")]),
            ),
            replicas=2,
        ),
        status=client.V1DeploymentStatus(available_replicas=1, replicas=2),
    )

    findings = find_deployment_issues([deployment])

    assert findings[0]["resourceKind"] == "Deployment"
    assert findings[0]["severity"] == "warning"


def test_detects_not_ready_node() -> None:
    node = client.V1Node(
        metadata=client.V1ObjectMeta(name="worker-1"),
        status=client.V1NodeStatus(
            conditions=[client.V1NodeCondition(type="Ready", status="False")]
        ),
    )

    findings = find_node_issues([node])

    assert findings[0]["resourceKind"] == "Node"
    assert findings[0]["severity"] == "critical"


def test_detects_pending_pvc() -> None:
    pvc = client.V1PersistentVolumeClaim(
        metadata=client.V1ObjectMeta(name="data", namespace="default"),
        spec=client.V1PersistentVolumeClaimSpec(storage_class_name="standard"),
        status=client.V1PersistentVolumeClaimStatus(phase="Pending"),
    )

    findings = find_pvc_issues([pvc])

    assert findings[0]["resourceKind"] == "PersistentVolumeClaim"
    assert findings[0]["severity"] == "warning"


def test_detects_service_without_endpoints() -> None:
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name="api", namespace="default"),
        spec=client.V1ServiceSpec(type="ClusterIP", cluster_ip="10.0.0.1", ports=[]),
    )
    endpoint = client.V1Endpoints(
        metadata=client.V1ObjectMeta(name="api", namespace="default"), subsets=[]
    )

    findings = find_service_issues([service], [endpoint])

    assert findings[0]["resourceKind"] == "Service"
    assert findings[0]["severity"] == "warning"
