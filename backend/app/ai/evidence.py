from typing import Any

SEVERITY_SCORE = {"critical": 40, "warning": 20, "info": 5}
REASON_SCORE = {
    "CrashLoopBackOff": 50,
    "OOMKilled": 45,
    "ImagePullBackOff": 40,
    "ErrImagePull": 40,
    "Pending": 30,
    "Failed": 35,
}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _limit_text(value: Any, limit: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def _resource_id(kind: str, namespace: str | None, name: str | None) -> str:
    if namespace and name:
        return f"{kind}/{namespace}/{name}"
    if name:
        return f"{kind}/{name}"
    return kind


def _pod_score(pod: dict[str, Any]) -> int:
    reason = pod.get("waitingReason")
    score = REASON_SCORE.get(str(reason), 0)
    if not pod.get("ready"):
        score += 15
    score += min(_as_int(pod.get("restarts")), 20)
    if pod.get("phase") in {"Pending", "Failed"}:
        score += REASON_SCORE.get(str(pod.get("phase")), 0)
    return score


def _severity_from_score(score: int) -> str:
    if score >= 50:
        return "critical"
    if score >= 20:
        return "warning"
    return "info"


def _signal(
    signal_id: str,
    kind: str,
    namespace: str | None,
    name: str | None,
    severity: str,
    score: int,
    symptoms: list[str],
    evidence: list[str],
    recommended_tools: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": signal_id,
        "resource": _resource_id(kind, namespace, name),
        "kind": kind,
        "namespace": namespace,
        "name": name,
        "severity": severity,
        "score": score,
        "symptoms": [item for item in symptoms if item],
        "evidence": [_limit_text(item) for item in evidence if item],
        "recommendedTools": recommended_tools or [],
    }


def _pod_signal(index: int, pod: dict[str, Any]) -> dict[str, Any] | None:
    score = _pod_score(pod)
    if score <= 0:
        return None
    namespace = pod.get("namespace")
    name = pod.get("name")
    reason = pod.get("waitingReason")
    phase = pod.get("phase")
    restarts = _as_int(pod.get("restarts"))
    symptoms = [f"phase={phase}", f"ready={pod.get('ready')}"]
    evidence = []
    tools = ["get_events"]
    if reason:
        symptoms.append(f"waitingReason={reason}")
    if restarts:
        symptoms.append(f"restarts={restarts}")
    if reason in {"CrashLoopBackOff", "OOMKilled"} or restarts >= 5:
        tools.extend(["get_pod_details", "get_logs"])
    elif reason in {"ImagePullBackOff", "ErrImagePull"} or phase == "Pending":
        tools.append("get_pod_details")
    for container in pod.get("containers") or []:
        if isinstance(container, dict) and container.get("name"):
            evidence.append(f"container={container.get('name')}")
    return _signal(
        f"S{index}",
        "Pod",
        str(namespace) if namespace else None,
        str(name) if name else None,
        _severity_from_score(score),
        score,
        symptoms,
        evidence,
        tools,
    )


def _finding_signal(index: int, finding: dict[str, Any]) -> dict[str, Any]:
    severity = str(finding.get("severity") or "info")
    score = SEVERITY_SCORE.get(severity, 5)
    evidence = [str(item) for item in finding.get("evidence") or []]
    recommendation = finding.get("recommendation")
    if recommendation:
        evidence.append(f"recommendation={recommendation}")
    return _signal(
        f"S{index}",
        str(finding.get("resourceKind") or "Resource"),
        str(finding.get("namespace")) if finding.get("namespace") else None,
        str(finding.get("resourceName")) if finding.get("resourceName") else None,
        severity,
        score,
        [str(finding.get("summary") or "")],
        evidence,
        [],
    )


def _deployment_signal(index: int, deployment: dict[str, Any]) -> dict[str, Any] | None:
    if deployment.get("available") is not False:
        return None
    return _signal(
        f"S{index}",
        "Deployment",
        str(deployment.get("namespace")) if deployment.get("namespace") else None,
        str(deployment.get("name")) if deployment.get("name") else None,
        "warning",
        28,
        ["available=false"],
        [
            f"desiredReplicas={deployment.get('desiredReplicas')}",
            f"availableReplicas={deployment.get('availableReplicas')}",
        ],
        ["get_pods", "get_events"],
    )


def _pvc_signal(index: int, pvc: dict[str, Any]) -> dict[str, Any] | None:
    if pvc.get("phase") != "Pending":
        return None
    return _signal(
        f"S{index}",
        "PersistentVolumeClaim",
        str(pvc.get("namespace")) if pvc.get("namespace") else None,
        str(pvc.get("name")) if pvc.get("name") else None,
        "warning",
        30,
        ["phase=Pending"],
        [f"storageClassName={pvc.get('storageClassName')}", f"requestedStorage={pvc.get('requestedStorage')}"],
        ["get_events"],
    )


def _tool_evidence(tool_results: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    compact = []
    for item in tool_results[:limit]:
        result = item.get("result")
        if isinstance(result, str):
            result = _limit_text(result, 500)
        elif isinstance(result, dict):
            result = {key: value for key, value in result.items() if key in {"phase", "containers", "containerSpecs", "status", "reason"}}
        compact.append(
            {
                "tool": item.get("tool"),
                "status": item.get("status"),
                "params": item.get("params") or {},
                "result": result,
            }
        )
    return compact


def compile_evidence_pack(
    snapshot: dict[str, Any],
    tool_results: list[dict[str, Any]] | None = None,
    max_signals: int = 12,
    max_tool_results: int = 8,
) -> dict[str, Any]:
    resources = snapshot.get("resources") or {}
    signals: list[dict[str, Any]] = []
    next_id = 1

    for pod in resources.get("pods") or []:
        if not isinstance(pod, dict):
            continue
        signal = _pod_signal(next_id, pod)
        if signal:
            signals.append(signal)
            next_id += 1

    for deployment in resources.get("deployments") or []:
        if not isinstance(deployment, dict):
            continue
        signal = _deployment_signal(next_id, deployment)
        if signal:
            signals.append(signal)
            next_id += 1

    for pvc in resources.get("pvcs") or []:
        if not isinstance(pvc, dict):
            continue
        signal = _pvc_signal(next_id, pvc)
        if signal:
            signals.append(signal)
            next_id += 1

    for finding in snapshot.get("findings") or []:
        if isinstance(finding, dict):
            signals.append(_finding_signal(next_id, finding))
            next_id += 1

    signals.sort(key=lambda item: int(item.get("score") or 0), reverse=True)
    compact_signals = signals[:max_signals]
    overflow = max(0, len(signals) - len(compact_signals))
    severity_counts = {"critical": 0, "warning": 0, "info": 0}
    for signal in signals:
        severity = str(signal.get("severity") or "info")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    return {
        "namespaceFilter": snapshot.get("namespaceFilter"),
        "summary": snapshot.get("summary"),
        "signalCounts": {
            "total": len(signals),
            "included": len(compact_signals),
            "overflow": overflow,
            **severity_counts,
        },
        "signals": compact_signals,
        "toolEvidence": _tool_evidence(tool_results or [], max_tool_results),
        "guidance": [
            "Use signals as the primary compact evidence pack.",
            "Deep-dive the highest impact signals first; summarize lower priority overflow.",
            "Only call extra tools when a top signal lacks enough evidence for cause or confidence.",
        ],
    }
