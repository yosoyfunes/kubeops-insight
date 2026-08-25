from typing import Any

from app.ai.agent import AgentLimitExceeded, run_kubernetes_agent
from app.ai.cache import ai_response_cache, cache_key
from app.ai.evidence import compile_evidence_pack
from app.ai.prompt import build_analysis_prompt, build_chat_prompt
from app.ai.provider import LLMProviderError, get_llm_provider
from app.ai.tools import run_diagnostic_tools
from app.config.settings import get_settings
from app.kubernetes import service as kubernetes_service
from app.metrics.provider import get_metrics_summary

COMMAND_MARKERS = (
    "no puedo ejecutar comandos",
    "kubectl",
    " helm ",
    " ejecutar",
    "ejecutar:",
    " correr",
    "run ",
    "describe pod",
    "get events",
    " logs ",
)

COMMAND_DISCLAIMERS = (
    "No puedo ejecutar comandos. Sin embargo, ",
    "No puedo ejecutar comandos. ",
    "No puedo ejecutar comandos, pero ",
)


def _top_items(items: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    return items[:limit]


def _contains_command_marker(value: Any) -> bool:
    text = str(value).lower()
    return any(marker in text for marker in COMMAND_MARKERS)


def _clean_human_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if not _contains_command_marker(item)]


def _clean_answer_text(value: Any) -> str:
    text = str(value)
    for disclaimer in COMMAND_DISCLAIMERS:
        if text.startswith(disclaimer):
            return text.removeprefix(disclaimer)
    return text


def _llm_error_response(exc: Exception) -> dict[str, Any]:
    return {
        "answer": "No pude completar la llamada al modelo. Reintentá o reducí el alcance del análisis.",
        "confidence": "low",
        "evidence": [str(exc)[:240]],
        "readOnlyCommands": [],
        "missingData": ["Respuesta válida del proveedor LLM"],
    }


def _agent_limit_response(exc: AgentLimitExceeded) -> dict[str, Any]:
    return {
        "answer": "La investigación se detuvo por límites de seguridad del agente.",
        "confidence": "low",
        "evidence": [f"finishReason={exc.reason}"],
        "readOnlyCommands": [],
        "missingData": ["Reducir el alcance de la consulta o ajustar los límites del agente."],
    }


def _provider_status(settings: Any) -> str:
    return str(settings.llm_provider or "bedrock")


def _normalize_chat_answer(answer: dict[str, Any]) -> dict[str, Any]:
    if isinstance(answer.get("answer"), str):
        return {
            **answer,
            "answer": _clean_answer_text(answer.get("answer")),
            "evidence": _clean_human_list(answer.get("evidence")),
            "readOnlyCommands": [],
            "missingData": _clean_human_list(answer.get("missingData")),
        }
    return {
        "answer": _clean_answer_text(answer.get("summary") or "No pude generar una respuesta conversacional."),
        "confidence": str(answer.get("confidence") or "low"),
        "evidence": _clean_human_list(answer.get("evidence")),
        "readOnlyCommands": [],
        "missingData": _clean_human_list(answer.get("missingData")),
    }


def _with_evidence_coverage(answer: dict[str, Any], evidence_pack: dict[str, Any]) -> dict[str, Any]:
    counts = evidence_pack.get("signalCounts") or {}
    overflow = int(counts.get("overflow") or 0)
    included = int(counts.get("included") or 0)
    total = int(counts.get("total") or 0)
    if overflow <= 0 or total <= 0:
        return answer
    note = (
        f"Cobertura: se priorizaron {included} de {total} señales detectadas; "
        f"{overflow} quedaron resumidas sin investigación profunda por presupuesto de análisis."
    )
    evidence = list(answer.get("evidence") or [])
    if note not in evidence:
        evidence.append(note)
    return {**answer, "evidence": evidence}


def _normalize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    issues = []
    for issue in analysis.get("prioritizedIssues", []):
        if not isinstance(issue, dict):
            continue
        issues.append(
            {
                **issue,
                "evidence": _clean_human_list(issue.get("evidence")),
                "hypotheses": _clean_human_list(issue.get("hypotheses")),
                "recommendedNextSteps": [],
                "readOnlyCommands": [],
            }
        )
    return {
        **analysis,
        "prioritizedIssues": issues,
        "missingData": _clean_human_list(analysis.get("missingData")),
        "safeToIgnore": _clean_human_list(analysis.get("safeToIgnore")),
    }


def _filter_findings(findings: list[dict[str, Any]], namespace: str | None = None) -> list[dict[str, Any]]:
    if not namespace:
        return findings
    return [finding for finding in findings if finding.get("namespace") == namespace]


def _namespace_from_question(question: str, snapshot: dict[str, Any]) -> str | None:
    pods = snapshot.get("resources", {}).get("pods", [])
    question_lower = question.lower()
    matched_namespaces = {
        pod.get("namespace")
        for pod in pods
        if isinstance(pod.get("name"), str) and pod["name"].lower() in question_lower
    }
    matched_namespaces.discard(None)
    if len(matched_namespaces) == 1:
        return str(next(iter(matched_namespaces)))

    if "crashloop" in question_lower or "crashloopbackoff" in question_lower:
        crashloop_namespaces = {
            pod.get("namespace")
            for pod in pods
            if pod.get("waitingReason") == "CrashLoopBackOff"
            or (not pod.get("ready") and int(pod.get("restarts") or 0) > 0)
        }
        crashloop_namespaces.discard(None)
        if len(crashloop_namespaces) == 1:
            return str(next(iter(crashloop_namespaces)))
    return None


async def build_cluster_snapshot(namespace: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    summary = await kubernetes_service.get_cluster_summary()
    findings = _filter_findings(await kubernetes_service.get_findings(), namespace)
    pods = await kubernetes_service.list_pods(namespace)
    deployments = await kubernetes_service.list_deployments(namespace)
    services = await kubernetes_service.list_services(namespace)
    pvcs = await kubernetes_service.list_pvcs(namespace)
    events = await kubernetes_service.list_events(namespace, limit=20, minutes=60)
    metrics = await get_metrics_summary()

    return {
        "namespaceFilter": namespace,
        "summary": summary,
        "findings": _top_items(findings, settings.ai_max_findings),
        "resources": {
            "pods": _top_items(pods, settings.ai_max_resources),
            "deployments": _top_items(deployments, settings.ai_max_resources),
            "services": _top_items(services, settings.ai_max_resources),
            "pvcs": _top_items(pvcs, settings.ai_max_resources),
            "events": _top_items(events, settings.ai_max_events),
        },
        "metrics": metrics,
    }


async def analyze_cluster(namespace: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    provider_status = _provider_status(settings)
    key = cache_key("analyze", {"namespace": namespace, "provider": provider_status})
    cached = ai_response_cache.get(key, settings.ai_cache_ttl_seconds)
    if cached:
        return cached

    snapshot = await build_cluster_snapshot(namespace)
    tool_results = []
    if namespace:
        tool_results = await run_diagnostic_tools(
            snapshot, namespace, settings.ai_max_tools_per_chat, settings.ai_max_log_tail_lines
        )
        snapshot["diagnosticToolResults"] = tool_results
    prompt = build_analysis_prompt(snapshot)
    provider = get_llm_provider(settings)
    try:
        analysis = _normalize_analysis(await provider.generate(prompt))
    except (LLMProviderError, ValueError) as exc:
        analysis = {
            "summary": "No pude completar el análisis con el modelo.",
            "overallSeverity": "info",
            "prioritizedIssues": [],
            "missingData": [str(exc)[:240]],
            "safeToIgnore": [],
        }
    return ai_response_cache.set(
        key,
        {
            "provider": settings.llm_provider,
            "analysis": analysis,
            "toolsUsed": tool_results,
        },
    )


def ai_status() -> dict[str, Any]:
    settings = get_settings()
    return {
        "provider": _provider_status(settings),
    }


async def chat(question: str, namespace: str | None = None) -> dict[str, Any]:
    settings = get_settings()
    provider_status = _provider_status(settings)
    key = cache_key(
        "chat", {"question": question, "namespace": namespace, "provider": provider_status}
    )
    cached = ai_response_cache.get(key, settings.ai_cache_ttl_seconds)
    if cached:
        return cached

    snapshot = await build_cluster_snapshot(namespace)
    tool_results = []
    tool_namespace = namespace or _namespace_from_question(question, snapshot)
    tool_results = await run_diagnostic_tools(
        snapshot, tool_namespace, settings.ai_max_tools_per_chat, settings.ai_max_log_tail_lines
    )
    snapshot["diagnosticToolResults"] = tool_results
    evidence_pack = compile_evidence_pack(snapshot, tool_results, settings.ai_max_findings)
    if settings.llm_provider == "bedrock":
        try:
            agent_result = await run_kubernetes_agent(question, settings, evidence_pack)
            answer = _with_evidence_coverage(
                _normalize_chat_answer(agent_result["answer"]), evidence_pack
            )
            return ai_response_cache.set(
                key,
                {
                    "provider": settings.llm_provider,
                    "answer": answer,
                    "toolsUsed": agent_result["toolsUsed"],
                    "agentMetrics": agent_result["agentMetrics"],
                    "evidencePack": agent_result.get("evidencePack"),
                },
            )
        except AgentLimitExceeded as exc:
            answer = _agent_limit_response(exc)
            return ai_response_cache.set(
                key,
                {
                    "provider": settings.llm_provider,
                    "answer": answer,
                    "toolsUsed": [],
                    "agentMetrics": {
                        "cycles": 0,
                        "toolsExecuted": [],
                        "inputTokens": 0,
                        "outputTokens": 0,
                        "durationMs": 0,
                        "provider": settings.llm_provider,
                        "model": settings.bedrock_model_id,
                        "estimatedCost": 0,
                        "finishReason": exc.reason,
                    },
                },
            )
        except LLMProviderError as exc:
            answer = _llm_error_response(exc)
            return ai_response_cache.set(
                key,
                {
                    "provider": settings.llm_provider,
                    "answer": answer,
                    "toolsUsed": [],
                },
            )
    prompt = build_chat_prompt(question, snapshot)
    provider = get_llm_provider(settings)
    try:
        answer = _normalize_chat_answer(await provider.generate(prompt))
    except (LLMProviderError, ValueError) as exc:
        answer = _llm_error_response(exc)
    return ai_response_cache.set(
        key,
        {
            "provider": settings.llm_provider,
            "answer": answer,
            "toolsUsed": tool_results,
        },
    )
