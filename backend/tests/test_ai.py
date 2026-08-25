import asyncio
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.ai.agent import AgentLimitExceeded, run_kubernetes_agent
from app.ai.cache import ai_response_cache
from app.ai.evidence import compile_evidence_pack
from app.ai.prompt import build_analysis_prompt, build_chat_prompt
from app.ai.provider import (
    LLMProviderError,
    OpenAICompatibleProvider,
    create_bedrock_client,
    parse_json_response,
)
from app.ai.service import (
    _namespace_from_question,
    _normalize_analysis,
    _normalize_chat_answer,
    _with_evidence_coverage,
    analyze_cluster,
    chat,
)
from app.ai.tools import _normalize_log_text, run_diagnostic_tools
from app.config.settings import Settings
from app.main import app

client = TestClient(app)


def test_prompt_requires_json_only_output() -> None:
    prompt = build_analysis_prompt({"summary": {"cluster": {"status": "healthy"}}})

    assert "Return raw JSON only" in prompt
    assert "Do not invent resources" in prompt
    assert "Cluster snapshot" in prompt


def test_chat_prompt_answers_in_spanish() -> None:
    prompt = build_chat_prompt("Que pods fallan?", {"findings": []})

    assert "Answer in Spanish" in prompt
    assert "Que pods fallan?" in prompt
    assert "already executed read-only investigation" in prompt


async def _fake_tool_result(name: str) -> dict[str, object]:
    return {"tool": name, "status": "ok", "params": {}, "result": {}}


def test_run_diagnostic_tools_skips_without_namespace() -> None:
    response = asyncio.run(run_diagnostic_tools({"findings": []}, None))

    assert response == []


def test_run_diagnostic_tools_limits_tool_count(monkeypatch) -> None:
    snapshot = {
        "findings": [
            {"resourceKind": "Pod", "resourceName": f"pod-{index}"}
            for index in range(12)
        ],
        "resources": {"pods": [{"name": f"pod-{index}", "containers": []} for index in range(12)]},
    }

    async def fake_events(namespace: str) -> dict[str, object]:
        return await _fake_tool_result(f"events-{namespace}")

    async def fake_pod(namespace: str, pod_name: str) -> dict[str, object]:
        return await _fake_tool_result(f"pod-{pod_name}-{namespace}")

    async def fake_logs(
        namespace: str, pod_name: str, container: str | None = None, tail_lines: int = 50
    ) -> dict[str, object]:
        return await _fake_tool_result(f"logs-{pod_name}-{namespace}-{container}-{tail_lines}")

    monkeypatch.setattr("app.ai.tools.get_namespace_events", fake_events)
    monkeypatch.setattr("app.ai.tools.get_pod_details", fake_pod)
    monkeypatch.setattr("app.ai.tools.get_pod_logs", fake_logs)

    response = asyncio.run(run_diagnostic_tools(snapshot, "default", max_tools=8))

    assert len(response) == 8


def test_run_diagnostic_tools_checks_degraded_pods_without_findings(monkeypatch) -> None:
    snapshot = {
        "findings": [],
        "resources": {
            "pods": [
                {
                    "name": "crashloop-api-b7b698bd8-nfwvs",
                    "ready": False,
                    "waitingReason": None,
                    "restarts": 115,
                    "containers": [{"name": "api"}],
                }
            ]
        },
    }

    async def fake_events(namespace: str) -> dict[str, object]:
        return await _fake_tool_result(f"events-{namespace}")

    async def fake_pod(namespace: str, pod_name: str) -> dict[str, object]:
        return await _fake_tool_result(f"pod-{pod_name}-{namespace}")

    async def fake_logs(
        namespace: str, pod_name: str, container: str | None = None, tail_lines: int = 50
    ) -> dict[str, object]:
        return await _fake_tool_result(f"logs-{pod_name}-{namespace}-{container}-{tail_lines}")

    monkeypatch.setattr("app.ai.tools.get_namespace_events", fake_events)
    monkeypatch.setattr("app.ai.tools.get_pod_details", fake_pod)
    monkeypatch.setattr("app.ai.tools.get_pod_logs", fake_logs)

    response = asyncio.run(run_diagnostic_tools(snapshot, "klm-sample-apps", max_tools=8))

    assert [item["tool"] for item in response] == [
        "events-klm-sample-apps",
        "pod-crashloop-api-b7b698bd8-nfwvs-klm-sample-apps",
        "logs-crashloop-api-b7b698bd8-nfwvs-klm-sample-apps-api-50",
    ]


def test_namespace_from_question_uses_mentioned_pod() -> None:
    snapshot = {
        "resources": {
            "pods": [
                {"name": "crashloop-api-b7b698bd8-nfwvs", "namespace": "klm-sample-apps"}
            ]
        }
    }

    namespace = _namespace_from_question(
        "Que pasa con crashloop-api-b7b698bd8-nfwvs?", snapshot
    )

    assert namespace == "klm-sample-apps"


def test_namespace_from_question_uses_single_crashloop_namespace() -> None:
    snapshot = {
        "resources": {
            "pods": [
                {
                    "name": "crashloop-api-b7b698bd8-nfwvs",
                    "namespace": "klm-sample-apps",
                    "ready": False,
                    "restarts": 116,
                    "waitingReason": "CrashLoopBackOff",
                },
                {
                    "name": "healthy-api",
                    "namespace": "default",
                    "ready": True,
                    "restarts": 0,
                    "waitingReason": None,
                },
            ]
        }
    }

    namespace = _namespace_from_question(
        "corre los comandos necesarios para diagnosticar exactamente el error de CrashLoopBackOff",
        snapshot,
    )

    assert namespace == "klm-sample-apps"


def test_normalize_chat_answer_removes_command_disclaimer() -> None:
    response = _normalize_chat_answer(
        {
            "answer": "No puedo ejecutar comandos. Sin embargo, el pod está en CrashLoopBackOff.",
            "confidence": "high",
            "evidence": [],
            "missingData": [],
        }
    )

    assert response["answer"] == "el pod está en CrashLoopBackOff."


def test_normalize_log_text_decodes_byte_literals() -> None:
    assert _normalize_log_text(b"line one\n") == "line one\n"
    assert _normalize_log_text("b'line two\\n'") == "line two\n"


def test_normalize_analysis_removes_user_shell_work() -> None:
    analysis = _normalize_analysis(
        {
            "summary": "resumen",
            "overallSeverity": "warning",
            "prioritizedIssues": [
                {
                    "title": "pod fallando",
                    "severity": "critical",
                    "resources": ["Pod/ns/name"],
                    "evidence": ["restartCount=4", "Ejecutar: kubectl logs name -n ns"],
                    "hypotheses": ["crash confirmado", "correr kubectl describe pod"],
                    "recommendedNextSteps": ["kubectl describe pod name -n ns"],
                    "readOnlyCommands": ["kubectl logs name -n ns"],
                    "confidence": "high",
                }
            ],
            "missingData": ["logs previos", "kubectl get events"],
            "safeToIgnore": [],
        }
    )

    issue = analysis["prioritizedIssues"][0]
    assert issue["evidence"] == ["restartCount=4"]
    assert issue["hypotheses"] == ["crash confirmado"]
    assert issue["recommendedNextSteps"] == []
    assert issue["readOnlyCommands"] == []
    assert analysis["missingData"] == ["logs previos"]


def test_compile_evidence_pack_prioritizes_degraded_runtime_signals() -> None:
    snapshot = {
        "namespaceFilter": None,
        "summary": {"cluster": {"status": "degraded"}},
        "resources": {
            "pods": [
                {
                    "name": "healthy-api",
                    "namespace": "default",
                    "phase": "Running",
                    "ready": True,
                    "restarts": 0,
                    "waitingReason": None,
                },
                {
                    "name": "crashloop-api-b7b698bd8-nfwvs",
                    "namespace": "klm-sample-apps",
                    "phase": "Running",
                    "ready": False,
                    "restarts": 396,
                    "waitingReason": "CrashLoopBackOff",
                    "containers": [{"name": "api"}],
                },
            ],
            "deployments": [
                {
                    "name": "crashloop-api",
                    "namespace": "klm-sample-apps",
                    "available": False,
                    "desiredReplicas": 1,
                    "availableReplicas": 0,
                }
            ],
            "pvcs": [],
        },
        "findings": [
            {
                "severity": "info",
                "resourceKind": "Pod",
                "resourceName": "healthy-api",
                "namespace": "default",
                "summary": "Container uses latest image tag.",
                "evidence": ["image=nginx:latest"],
            }
        ],
    }

    evidence_pack = compile_evidence_pack(snapshot, [], max_signals=2)

    assert evidence_pack["signalCounts"]["total"] == 3
    assert evidence_pack["signalCounts"]["included"] == 2
    assert evidence_pack["signalCounts"]["overflow"] == 1
    assert evidence_pack["signals"][0]["resource"] == "Pod/klm-sample-apps/crashloop-api-b7b698bd8-nfwvs"
    assert evidence_pack["signals"][0]["severity"] == "critical"
    assert "get_logs" in evidence_pack["signals"][0]["recommendedTools"]


def test_compile_evidence_pack_compacts_tool_results() -> None:
    evidence_pack = compile_evidence_pack(
        {"resources": {}, "findings": []},
        [
            {
                "tool": "get_pod_logs",
                "status": "ok",
                "params": {"pod": "api"},
                "result": "line\n" * 300,
            }
        ],
    )

    assert evidence_pack["toolEvidence"][0]["tool"] == "get_pod_logs"
    assert len(evidence_pack["toolEvidence"][0]["result"]) <= 500


def test_evidence_coverage_note_is_added_deterministically() -> None:
    answer = {"answer": "Hay errores críticos.", "evidence": [], "missingData": []}
    evidence_pack = {"signalCounts": {"total": 25, "included": 12, "overflow": 13}}

    response = _with_evidence_coverage(answer, evidence_pack)

    assert response["evidence"] == [
        "Cobertura: se priorizaron 12 de 25 señales detectadas; 13 quedaron resumidas sin investigación profunda por presupuesto de análisis."
    ]


def test_parse_json_response_accepts_markdown_fences() -> None:
    response = parse_json_response(
        '```json\n{"overallSeverity": "info", "commands": ["kubectl get pods -A"]}\n```\nextra'
    )

    assert response["overallSeverity"] == "info"


def test_parse_json_response_falls_back_to_structured_text() -> None:
    response = parse_json_response("Cluster status is healthy, but response was not JSON.")

    assert response["summary"] == "Cluster status is healthy, but response was not JSON."
    assert response["overallSeverity"] == "info"
    assert response["prioritizedIssues"] == []


def test_bedrock_client_uses_aws_profile(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeSession:
        def __init__(self, **kwargs) -> None:
            calls.append({"session": kwargs})

        def client(self, service_name: str, region_name: str):
            calls.append({"client": service_name, "region": region_name})
            return {"service": service_name}

    monkeypatch.setitem(sys.modules, "boto3", SimpleNamespace(Session=FakeSession))

    client = create_bedrock_client(Settings(aws_profile="demo-profile"))

    assert client == {"service": "bedrock-runtime"}
    assert calls[0] == {"session": {"profile_name": "demo-profile"}}
    assert calls[1] == {"client": "bedrock-runtime", "region": "us-east-1"}


def test_openai_compatible_provider_requires_configuration() -> None:
    provider = OpenAICompatibleProvider(Settings(llm_provider="openai-compatible"))

    try:
        asyncio.run(provider.generate("prompt"))
    except LLMProviderError as exc:
        assert "requires base URL and model" in str(exc)
    else:
        raise AssertionError("provider should require base URL and model")


def test_openai_compatible_provider_parses_chat_completion(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {"choices": [{"message": {"content": '{"answer":"ok"}'}}]}

    class FakeClient:
        def __init__(self, timeout: int) -> None:
            calls.append({"timeout": timeout})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback) -> None:
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, object]):
            calls.append({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    monkeypatch.setattr("app.ai.provider.httpx.AsyncClient", FakeClient)

    provider = OpenAICompatibleProvider(
        Settings(
            llm_provider="openai-compatible",
            openai_compatible_base_url="https://llm.example/v1/",
            openai_compatible_model="demo-model",
            openai_compatible_api_key="secret",
        )
    )

    response = asyncio.run(provider.generate("prompt"))

    assert response == {"answer": "ok"}
    assert calls[1]["url"] == "https://llm.example/v1/chat/completions"
    assert calls[1]["headers"] == {
        "Content-Type": "application/json",
        "Authorization": "Bearer secret",
    }
    assert calls[1]["json"]["model"] == "demo-model"


class FakeAgentMetrics:
    def __init__(self, summary: dict[str, object]) -> None:
        self.summary = summary

    def get_summary(self) -> dict[str, object]:
        return self.summary


class FakeAgentResult:
    def __init__(self, message: dict[str, object], summary: dict[str, object]) -> None:
        self.message = message
        self.metrics = FakeAgentMetrics(summary)


def test_kubernetes_agent_returns_answer_tools_and_metrics(monkeypatch) -> None:
    class FakeAgent:
        async def invoke_async(self, question: str) -> FakeAgentResult:
            assert question == "por qué falla nginx?"
            return FakeAgentResult(
                {
                    "content": [
                        {
                            "text": '{"answer":"nginx falla por ImagePullBackOff","confidence":"high","evidence":["evento de pull"],"readOnlyCommands":[],"missingData":[]}'
                        }
                    ]
                },
                {
                    "total_cycles": 3,
                    "total_duration": 1.2,
                    "accumulated_usage": {"inputTokens": 1000, "outputTokens": 200},
                    "tool_usage": {
                        "find_unhealthy_workloads": {
                            "execution_stats": {"call_count": 1, "error_count": 0}
                        },
                        "get_events": {"execution_stats": {"call_count": 1, "error_count": 0}},
                    },
                },
            )

    monkeypatch.setattr("app.ai.agent._build_agent", lambda settings, tools: FakeAgent())

    response = asyncio.run(
        run_kubernetes_agent(
            "por qué falla nginx?",
            Settings(llm_provider="bedrock", agent_max_cycles=5),
        )
    )

    assert response["answer"]["answer"] == "nginx falla por ImagePullBackOff"
    assert response["toolsUsed"] == [
        {"tool": "find_unhealthy_workloads", "status": "ok", "params": {}},
        {"tool": "get_events", "status": "ok", "params": {}},
    ]
    assert response["agentMetrics"]["cycles"] == 3
    assert response["agentMetrics"]["inputTokens"] == 1000


def test_kubernetes_agent_enforces_max_cycles(monkeypatch) -> None:
    class FakeAgent:
        async def invoke_async(self, question: str) -> FakeAgentResult:
            return FakeAgentResult(
                {"content": [{"text": '{"answer":"ok","confidence":"low","evidence":[],"missingData":[]}'}]},
                {
                    "total_cycles": 6,
                    "accumulated_usage": {"inputTokens": 10, "outputTokens": 10},
                    "tool_usage": {},
                },
            )

    monkeypatch.setattr("app.ai.agent._build_agent", lambda settings, tools: FakeAgent())

    try:
        asyncio.run(
            run_kubernetes_agent(
                "pregunta", Settings(llm_provider="bedrock", agent_max_cycles=5)
            )
        )
    except AgentLimitExceeded as exc:
        assert exc.reason == "max_cycles"
    else:
        raise AssertionError("agent should stop when max cycles is exceeded")


def test_kubernetes_agent_enforces_timeout(monkeypatch) -> None:
    class SlowAgent:
        async def invoke_async(self, question: str) -> FakeAgentResult:
            await asyncio.sleep(0.05)
            return FakeAgentResult({"content": [{"text": "{}"}]}, {})

    monkeypatch.setattr("app.ai.agent._build_agent", lambda settings, tools: SlowAgent())

    try:
        asyncio.run(
            run_kubernetes_agent(
                "pregunta", Settings(llm_provider="bedrock", agent_timeout_seconds=0)
            )
        )
    except AgentLimitExceeded as exc:
        assert exc.reason == "timeout"
    else:
        raise AssertionError("agent should stop on timeout")


def test_chat_response_is_cached(monkeypatch) -> None:
    ai_response_cache.clear()
    calls = {"provider": 0}
    settings = Settings(llm_provider="openai-compatible")

    async def fake_snapshot(namespace: str | None = None) -> dict[str, object]:
        return {"namespaceFilter": namespace, "findings": []}

    async def fake_tools(snapshot, namespace, max_tools=8, log_tail_lines=50):
        return []

    class FakeProvider:
        async def generate(self, prompt: str) -> dict[str, object]:
            calls["provider"] += 1
            return {
                "answer": "respuesta",
                "confidence": "high",
                "evidence": [],
                "readOnlyCommands": [],
                "missingData": [],
            }

    monkeypatch.setattr("app.ai.service.build_cluster_snapshot", fake_snapshot)
    monkeypatch.setattr("app.ai.service.run_diagnostic_tools", fake_tools)
    monkeypatch.setattr("app.ai.service.get_llm_provider", lambda settings: FakeProvider())
    monkeypatch.setattr("app.ai.service.get_settings", lambda: settings)

    first = asyncio.run(chat("pregunta cache", "default"))
    second = asyncio.run(chat("pregunta cache", "default"))

    assert first["cached"] is False
    assert second["cached"] is True
    assert calls["provider"] == 1


def test_bedrock_chat_passes_compact_evidence_pack_to_agent(monkeypatch) -> None:
    ai_response_cache.clear()
    settings = Settings(llm_provider="bedrock")
    captured: dict[str, object] = {}

    async def fake_snapshot(namespace: str | None = None) -> dict[str, object]:
        return {
            "namespaceFilter": namespace,
            "summary": {"cluster": {"status": "degraded"}},
            "resources": {
                "pods": [
                    {
                        "name": "api-123",
                        "namespace": "prod",
                        "phase": "Running",
                        "ready": False,
                        "restarts": 7,
                        "waitingReason": "CrashLoopBackOff",
                        "containers": [{"name": "api"}],
                    }
                ],
                "deployments": [],
                "pvcs": [],
            },
            "findings": [],
        }

    async def fake_tools(snapshot, namespace, max_tools=8, log_tail_lines=50):
        return []

    async def fake_agent(question: str, settings: Settings, evidence_pack: dict[str, object]):
        captured["question"] = question
        captured["evidencePack"] = evidence_pack
        return {
            "answer": {
                "answer": "api falla por CrashLoopBackOff",
                "confidence": "high",
                "evidence": ["waitingReason=CrashLoopBackOff"],
                "missingData": [],
            },
            "toolsUsed": [],
            "agentMetrics": {"cycles": 1},
            "evidencePack": evidence_pack,
        }

    monkeypatch.setattr("app.ai.service.get_settings", lambda: settings)
    monkeypatch.setattr("app.ai.service.build_cluster_snapshot", fake_snapshot)
    monkeypatch.setattr("app.ai.service.run_diagnostic_tools", fake_tools)
    monkeypatch.setattr("app.ai.service.run_kubernetes_agent", fake_agent)

    response = asyncio.run(chat("qué errores hay?", None))

    assert response["answer"]["answer"] == "api falla por CrashLoopBackOff"
    assert captured["evidencePack"]["signals"][0]["resource"] == "Pod/prod/api-123"
    assert response["evidencePack"]["signalCounts"]["critical"] == 1


def test_analyze_cluster_includes_live_tool_results(monkeypatch) -> None:
    ai_response_cache.clear()

    async def fake_snapshot(namespace: str | None = None) -> dict[str, object]:
        return {"namespaceFilter": namespace, "findings": []}

    async def fake_tools(snapshot, namespace, max_tools=8, log_tail_lines=50):
        return [{"tool": "get_namespace_events", "status": "ok", "params": {"namespace": namespace}}]

    class FakeProvider:
        async def generate(self, prompt: str) -> dict[str, object]:
            assert "diagnosticToolResults" in prompt
            return {
                "summary": "análisis",
                "overallSeverity": "info",
                "prioritizedIssues": [],
                "missingData": [],
                "safeToIgnore": [],
            }

    monkeypatch.setattr("app.ai.service.get_settings", lambda: Settings(llm_provider="openai-compatible"))
    monkeypatch.setattr("app.ai.service.build_cluster_snapshot", fake_snapshot)
    monkeypatch.setattr("app.ai.service.run_diagnostic_tools", fake_tools)
    monkeypatch.setattr("app.ai.service.get_llm_provider", lambda settings: FakeProvider())

    response = asyncio.run(analyze_cluster("prod"))

    assert response["toolsUsed"] == [
        {"tool": "get_namespace_events", "status": "ok", "params": {"namespace": "prod"}}
    ]
