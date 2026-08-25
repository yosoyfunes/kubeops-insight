from kubernetes import client

from app.kubernetes.summary import summarize_cluster


def test_summarize_cluster_counts_live_resources() -> None:
    ready_condition = client.V1NodeCondition(type="Ready", status="True")
    node = client.V1Node(status=client.V1NodeStatus(conditions=[ready_condition]))
    namespace = client.V1Namespace(metadata=client.V1ObjectMeta(name="default"))
    pod = client.V1Pod(
        metadata=client.V1ObjectMeta(name="api", namespace="default"),
        status=client.V1PodStatus(phase="Running", container_statuses=[]),
    )
    deployment = client.V1Deployment(
        metadata=client.V1ObjectMeta(name="api", namespace="default"),
        spec=client.V1DeploymentSpec(
            selector=client.V1LabelSelector(match_labels={"app": "api"}),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": "api"}),
                spec=client.V1PodSpec(containers=[client.V1Container(name="api", image="api")]),
            ),
            replicas=1,
        ),
        status=client.V1DeploymentStatus(available_replicas=1, replicas=1),
    )
    event = client.CoreV1Event(
        involved_object=client.V1ObjectReference(kind="Pod", name="api", namespace="default"),
        metadata=client.V1ObjectMeta(name="api-warning", namespace="default"),
        type="Warning",
    )

    summary = summarize_cluster([node], [namespace], [pod], [deployment], [event])

    assert summary["mode"] == "live"
    assert summary["cluster"]["nodes"] == 1
    assert summary["cluster"]["readyNodes"] == 1
    assert summary["cluster"]["pods"]["running"] == 1
    assert summary["cluster"]["deployments"]["available"] == 1
    assert summary["cluster"]["events"]["warningsLastHour"] == 1
