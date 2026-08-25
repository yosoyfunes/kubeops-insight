import json
from typing import Any, Protocol

import httpx
from fastapi.concurrency import run_in_threadpool

from app.config.settings import Settings


class LLMProvider(Protocol):
    async def generate(self, prompt: str) -> dict[str, Any]: ...


class LLMProviderError(RuntimeError):
    pass


class BedrockLLMProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, prompt: str) -> dict[str, Any]:
        try:
            response_text = await run_in_threadpool(self._invoke, prompt)
            return parse_json_response(response_text)
        except Exception as exc:
            msg = f"Bedrock provider failed: {exc}"
            raise LLMProviderError(msg) from exc

    def _invoke(self, prompt: str) -> str:
        client = create_bedrock_client(self.settings)
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.settings.bedrock_max_tokens,
            "temperature": self.settings.bedrock_temperature,
            "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        }
        response = client.invoke_model(
            modelId=self.settings.bedrock_model_id,
            body=json.dumps(body),
            accept="application/json",
            contentType="application/json",
        )
        payload = json.loads(response["body"].read())
        return payload["content"][0]["text"]


class OpenAICompatibleProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def generate(self, prompt: str) -> dict[str, Any]:
        if not self.settings.openai_compatible_base_url or not self.settings.openai_compatible_model:
            msg = "OpenAI-compatible provider requires base URL and model."
            raise LLMProviderError(msg)

        headers = {"Content-Type": "application/json"}
        if self.settings.openai_compatible_api_key:
            headers["Authorization"] = f"Bearer {self.settings.openai_compatible_api_key}"

        payload = {
            "model": self.settings.openai_compatible_model,
            "temperature": self.settings.bedrock_temperature,
            "max_tokens": self.settings.bedrock_max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(
                    f"{self.settings.openai_compatible_base_url.rstrip('/')}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
            return parse_json_response(body["choices"][0]["message"]["content"])
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            msg = f"OpenAI-compatible provider failed: {exc}"
            raise LLMProviderError(msg) from exc


def create_bedrock_client(settings: Settings) -> Any:
    import boto3

    session_kwargs: dict[str, str] = {}
    if settings.aws_profile:
        session_kwargs["profile_name"] = settings.aws_profile

    session = boto3.Session(**session_kwargs)
    return session.client("bedrock-runtime", region_name=settings.bedrock_region)


def parse_json_response(response_text: str) -> dict[str, Any]:
    stripped = response_text.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    if start == -1:
        return _structured_text_response(stripped)
    decoder = json.JSONDecoder()
    try:
        parsed, _ = decoder.raw_decode(stripped[start:])
        return parsed
    except json.JSONDecodeError:
        return _structured_text_response(stripped)


def _structured_text_response(response_text: str) -> dict[str, Any]:
    summary = response_text[:4000] or "El modelo no devolvió contenido."
    return {
        "summary": summary,
        "overallSeverity": "info",
        "prioritizedIssues": [],
        "missingData": ["El modelo respondió texto no estructurado en vez de JSON."],
        "safeToIgnore": [],
    }


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "bedrock":
        return BedrockLLMProvider(settings)
    if settings.llm_provider == "openai-compatible":
        return OpenAICompatibleProvider(settings)
    msg = f"Unsupported LLM provider: {settings.llm_provider}"
    raise ValueError(msg)
