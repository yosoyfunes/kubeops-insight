import asyncio
import json
import time
from typing import Any

import boto3

from app.ai.agent_tools import KubernetesAgentTools
from app.ai.provider import LLMProviderError, parse_json_response
from app.config.settings import Settings

AGENT_SYSTEM_PROMPT = """You are KubeOps Insight, a senior Kubernetes SRE diagnostic agent.

Answer in Spanish. Use only the provided tools and their results as evidence.
You must investigate with read-only tools before giving a final diagnosis unless the answer is already fully determined by prior tool output.
Never ask the user to run kubectl, shell commands, helm, scripts, or code.
Never claim you cannot execute commands. The platform executes safe read-only Kubernetes tools for you.
Do not invent namespaces, resources, logs, metrics, events, commands or actions.

Investigation guidance:
- When the user request is broad, reason from the compact evidence pack first instead of trying to enumerate every raw resource.
- Treat evidence pack signals as prioritized Kubernetes facts collected by the platform, not as user claims.
- Deep-dive only the highest impact signals when additional evidence is needed for root cause or confidence.
- If there are more signals than the response can cover deeply, summarize the overflow explicitly instead of expanding every item.
- If evidencePack.signalCounts.overflow is greater than 0, never call the analysis complete/exhaustive; state that you covered the highest-priority signals and summarize the remaining count.
- Do not overstate certainty for lower-priority signals that were not deep-dived with tool evidence.
- Start with find_unhealthy_workloads when the user names a workload or asks why something is failing.
- If the user asks about a failure but does not provide namespace or resource name, call find_unhealthy_workloads with no arguments before asking any clarification.
- Do not ask permission to scan the cluster with read-only tools. Read-only cluster investigation is your job.
- Use get_events when a pod/workload is Pending, ImagePullBackOff, scheduling related, PVC related, or unclear.
- Use get_pod_details for CrashLoopBackOff, OOMKilled, restarts, readiness failures or container state questions.
- Use get_logs only when pod details/events do not already explain the issue, or for CrashLoopBackOff/exit codes.
- Use get_metrics only for CPU, memory, OOM, pressure or saturation questions.
- Prefer deterministic Kubernetes states: CrashLoopBackOff, OOMKilled, ImagePullBackOff, DiskPressure, MemoryPressure, unavailable replicas and pending PVCs.
- Action tools are not available. If a remediation is appropriate, propose it as a future action requiring explicit confirmation.

CRITICAL: Write using ONLY plain text characters. Never use emoji symbols, Unicode pictographs, or decorative icons (🔴🟡🔍📋🛠️⚠️✅❌ etc). Use text labels instead.
CRITICAL: This is a CHAT/AGENT response. Return exactly these 5 keys: answer, confidence, evidence, readOnlyCommands, missingData.
Do NOT use the analysis shape (summary, overallSeverity, prioritizedIssues). That shape is for a different endpoint.
The "answer" field must be a plain Spanish prose string. Never nest JSON inside it.

Your entire response must be ONLY the JSON object itself, starting with { and ending with }.
Do not wrap it in Markdown code blocks (```json or ```).
Do not include any text before or after the JSON.

Required JSON shape (exactly these 5 keys, no others):
{
  "answer": "diagnóstico directo en prosa en español",
  "confidence": "high|medium|low",
  "evidence": ["hechos concretos de los resultados de herramientas"],
  "readOnlyCommands": [],
  "missingData": ["datos específicos faltantes si los hay"]
}
"""


def _agent_input(question: str, evidence_pack: dict[str, Any] | None = None) -> str:
    if not evidence_pack:
        return question
    return "\n".join(
        [
            "User question:",
            question,
            "",
            "Compact evidence pack collected before agent reasoning:",
            json.dumps(evidence_pack, ensure_ascii=False, separators=(",", ":")),
            "",
            "Use the compact evidence pack first. Call tools only to resolve important uncertainty.",
        ]
    )


BEDROCK_PRICE_PER_1K_TOKENS: dict[str, tuple[float, float]] = {
    "haiku": (0.0008, 0.004),
    "sonnet": (0.003, 0.015),
    "opus": (0.015, 0.075),
}


class AgentLimitExceeded(RuntimeError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _estimate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    model_key = model_id.lower()
    input_rate, output_rate = (0.003, 0.015)
    for key, rates in BEDROCK_PRICE_PER_1K_TOKENS.items():
        if key in model_key:
            input_rate, output_rate = rates
            break
    return round((input_tokens / 1000 * input_rate) + (output_tokens / 1000 * output_rate), 6)


def _extract_text_from_message(message: Any) -> str:
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, list):
            return "\n".join(str(block.get("text", "")) for block in content if isinstance(block, dict))
        return str(message)
    return str(message)


def _agent_result_text(result: Any) -> str:
    message = getattr(result, "message", None)
    if message is not None:
        return _extract_text_from_message(message)
    return str(result)


def _metrics_summary(result: Any) -> dict[str, Any]:
    metrics = getattr(result, "metrics", None)
    if metrics is None:
        return {}
    get_summary = getattr(metrics, "get_summary", None)
    if callable(get_summary):
        return get_summary()
    return {}


def _tools_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    tool_usage = summary.get("tool_usage", {})
    tools = []
    if not isinstance(tool_usage, dict):
        return tools
    for name, data in tool_usage.items():
        stats = (data or {}).get("execution_stats", {}) if isinstance(data, dict) else {}
        call_count = int(stats.get("call_count") or 0)
        status = "ok" if int(stats.get("error_count") or 0) == 0 else "error"
        for _ in range(call_count):
            tools.append({"tool": name, "status": status, "params": {}})
    return tools


def _agent_metrics(
    summary: dict[str, Any],
    settings: Settings,
    duration_ms: int,
    finish_reason: str,
) -> dict[str, Any]:
    usage = summary.get("accumulated_usage", {}) if isinstance(summary, dict) else {}
    input_tokens = int(usage.get("inputTokens") or 0)
    output_tokens = int(usage.get("outputTokens") or 0)
    estimated_cost = _estimate_cost(settings.bedrock_model_id, input_tokens, output_tokens)
    return {
        "cycles": int(summary.get("total_cycles") or 0) if isinstance(summary, dict) else 0,
        "toolsExecuted": [tool["tool"] for tool in _tools_from_summary(summary)],
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "durationMs": duration_ms,
        "provider": settings.llm_provider,
        "model": settings.bedrock_model_id,
        "estimatedCost": estimated_cost,
        "finishReason": finish_reason,
    }


def _create_bedrock_model(settings: Settings) -> Any:
    from strands.models import BedrockModel

    session_kwargs: dict[str, str] = {}
    if settings.aws_profile:
        session_kwargs["profile_name"] = settings.aws_profile
    session_kwargs["region_name"] = settings.bedrock_region
    session = boto3.Session(**session_kwargs)
    return BedrockModel(
        model_id=settings.bedrock_model_id,
        temperature=settings.bedrock_temperature,
        max_tokens=settings.agent_max_output_tokens,
        boto_session=session,
    )


def _build_agent(settings: Settings, tools: KubernetesAgentTools) -> Any:
    from strands import Agent

    model = _create_bedrock_model(settings)
    return Agent(
        model=model,
        system_prompt=AGENT_SYSTEM_PROMPT,
        tools=[
            tools.find_unhealthy_workloads,
            tools.get_cluster_summary,
            tools.get_pods,
            tools.get_deployment,
            tools.get_events,
            tools.get_pod_details,
            tools.get_logs,
            tools.get_metrics,
        ],
        callback_handler=None,
    )


async def run_kubernetes_agent(
    question: str, settings: Settings, evidence_pack: dict[str, Any] | None = None
) -> dict[str, Any]:
    agent_input = _agent_input(question, evidence_pack)
    initial_tokens = _estimate_tokens(agent_input) + _estimate_tokens(AGENT_SYSTEM_PROMPT)
    if initial_tokens > settings.agent_max_input_tokens:
        raise AgentLimitExceeded("max_input_tokens")
    if settings.agent_cost_enabled:
        initial_cost = _estimate_cost(settings.bedrock_model_id, initial_tokens, 0)
        if initial_cost > settings.agent_max_estimated_cost_per_request:
            raise AgentLimitExceeded("max_estimated_cost")

    tools = KubernetesAgentTools(
        max_items=settings.ai_max_resources,
        log_max_lines=settings.agent_log_max_lines,
        log_max_characters=settings.agent_log_max_characters,
    )
    agent = _build_agent(settings, tools)
    started = time.perf_counter()
    finish_reason = "completed"
    try:
        result = await asyncio.wait_for(
            agent.invoke_async(agent_input), timeout=settings.agent_timeout_seconds
        )
    except TimeoutError as exc:
        raise AgentLimitExceeded("timeout") from exc
    except Exception as exc:
        msg = f"Strands agent failed: {exc}"
        raise LLMProviderError(msg) from exc

    duration_ms = int((time.perf_counter() - started) * 1000)
    summary = _metrics_summary(result)
    metrics = _agent_metrics(summary, settings, duration_ms, finish_reason)
    if metrics["cycles"] > settings.agent_max_cycles:
        finish_reason = "max_cycles"
        raise AgentLimitExceeded(finish_reason)
    if metrics["inputTokens"] > settings.agent_max_input_tokens:
        finish_reason = "max_input_tokens"
        raise AgentLimitExceeded(finish_reason)
    if metrics["outputTokens"] > settings.agent_max_output_tokens:
        finish_reason = "max_output_tokens"
        raise AgentLimitExceeded(finish_reason)
    if settings.agent_cost_enabled and metrics["estimatedCost"] > settings.agent_max_estimated_cost_per_request:
        finish_reason = "max_estimated_cost"
        raise AgentLimitExceeded(finish_reason)

    text = _agent_result_text(result)
    answer = parse_json_response(text)
    return {
        "answer": answer,
        "toolsUsed": _tools_from_summary(summary),
        "agentMetrics": {**metrics, "finishReason": finish_reason},
        "evidencePack": evidence_pack,
    }
