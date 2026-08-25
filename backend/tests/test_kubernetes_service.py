from datetime import UTC, datetime, timedelta

from kubernetes import client

from app.kubernetes.service import _filter_recent_events, _pod_to_dict, _service_to_dict


def test_pod_to_dict_includes_readiness_and_waiting_reason() -> None:
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name="api", namespace="default"),
        spec=client.V1PodSpec(node_name="orbstack", containers=[client.V1Container(name="api")]),
        status=client.V1PodStatus(
            phase="Running",
            container_statuses=[
                client.V1ContainerStatus(
                    name="api",
                    image="api:latest",
                    image_id="api",
                    ready=False,
                    restart_count=3,
                    state=client.V1ContainerState(
                        waiting=client.V1ContainerStateWaiting(reason="ImagePullBackOff")
                    ),
                )
            ],
        ),
    )

    result = _pod_to_dict(pod)

    assert result["ready"] is False
    assert result["readyContainers"] == 0
    assert result["totalContainers"] == 1
    assert result["restarts"] == 3
    assert result["waitingReason"] == "ImagePullBackOff"


def test_service_to_dict_uses_kubernetes_external_ips_field() -> None:
    service = client.V1Service(
        metadata=client.V1ObjectMeta(name="api", namespace="default"),
        spec=client.V1ServiceSpec(
            type="ClusterIP",
            cluster_ip="10.0.0.1",
            external_ips=["192.0.2.10"],
            ports=[client.V1ServicePort(name="http", port=80, target_port=8080)],
        ),
    )

    result = _service_to_dict(service)

    assert result["externalIPs"] == ["192.0.2.10"]
    assert result["ports"][0]["targetPort"] == "8080"


def test_filter_recent_events_excludes_old_events() -> None:
    old_event = client.CoreV1Event(
        metadata=client.V1ObjectMeta(name="old", namespace="default"),
        involved_object=client.V1ObjectReference(kind="Pod", name="old", namespace="default"),
        last_timestamp=datetime.now(UTC) - timedelta(hours=2),
        type="Warning",
    )
    new_event = client.CoreV1Event(
        metadata=client.V1ObjectMeta(name="new", namespace="default"),
        involved_object=client.V1ObjectReference(kind="Pod", name="new", namespace="default"),
        last_timestamp=datetime.now(UTC),
        type="Warning",
    )

    result = _filter_recent_events([old_event, new_event], minutes=60, limit=10)

    assert [event.metadata.name for event in result] == ["new"]
