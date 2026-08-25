from app.metrics.provider import _parse_cpu_to_millicores, _parse_memory_to_mib


def test_parse_cpu_to_millicores() -> None:
    assert _parse_cpu_to_millicores("250m") == 250
    assert _parse_cpu_to_millicores("1") == 1000
    assert _parse_cpu_to_millicores("1000000n") == 1


def test_parse_memory_to_mib() -> None:
    assert _parse_memory_to_mib("128Mi") == 128
    assert _parse_memory_to_mib("1Gi") == 1024
