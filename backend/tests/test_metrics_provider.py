import asyncio

from kubernetes.client import ApiException

from app.metrics.provider import _parse_cpu_to_millicores, _parse_memory_to_mib, get_metrics_summary


def test_parse_cpu_to_millicores() -> None:
    assert _parse_cpu_to_millicores("250m") == 250
    assert _parse_cpu_to_millicores("1") == 1000
    assert _parse_cpu_to_millicores("1000000n") == 1


def test_parse_memory_to_mib() -> None:
    assert _parse_memory_to_mib("128Mi") == 128
    assert _parse_memory_to_mib("1Gi") == 1024


def test_metrics_summary_reports_unavailable_when_api_is_missing(monkeypatch) -> None:
    class FakeApi:
        def list_cluster_custom_object(self, *args):
            raise ApiException(status=404, reason="Not Found")

    monkeypatch.setattr("app.metrics.provider.get_custom_objects_api", lambda: FakeApi())

    response = asyncio.run(get_metrics_summary())

    assert response == {
        "provider": "metrics-server",
        "status": "unavailable",
        "reason": "Metrics API is not available in this cluster.",
    }


def test_metrics_summary_reports_unavailable_when_api_is_not_ready(monkeypatch) -> None:
    class FakeApi:
        def list_cluster_custom_object(self, *args):
            raise ApiException(status=503, reason="Service Unavailable")

    monkeypatch.setattr("app.metrics.provider.get_custom_objects_api", lambda: FakeApi())

    response = asyncio.run(get_metrics_summary())

    assert response["status"] == "unavailable"
    assert response["reason"] == "Metrics API is registered but not currently serving metrics."
    assert "HTTP 503" in response["details"]


def test_metrics_summary_reports_unavailable_on_request_failure(monkeypatch) -> None:
    class FakeApi:
        def list_cluster_custom_object(self, *args):
            raise TimeoutError("metrics request timed out")

    monkeypatch.setattr("app.metrics.provider.get_custom_objects_api", lambda: FakeApi())

    response = asyncio.run(get_metrics_summary())

    assert response["status"] == "unavailable"
    assert response["reason"] == "Metrics API request failed."
    assert "TimeoutError" in response["details"]
