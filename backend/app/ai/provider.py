import asyncio
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
        url = f"{self.settings.openai_compatible_base_url.rstrip('/')}/chat/completions"
        try:
            body = await self._post_chat_completion(url, headers, payload)
            return parse_json_response(body["choices"][0]["message"]["content"])
        except httpx.TimeoutException as exc:
            msg = f"OpenAI-compatible provider timed out after 60s calling {url}"
            raise LLMProviderError(msg) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            msg = (
                "OpenAI-compatible provider failed: "
                f"HTTP {exc.response.status_code} from {url}: {detail}"
            )
            raise LLMProviderError(msg) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            msg = f"OpenAI-compatible provider failed: {exc}"
            raise LLMProviderError(msg) from exc

    async def _post_chat_completion(
        self, url: str, headers: dict[str, str], payload: dict[str, Any]
    ) -> dict[str, Any]:
        last_error: httpx.HTTPError | None = None
        async with httpx.AsyncClient(timeout=60) as client:
            for attempt in range(3):
                try:
                    response = await client.post(url, headers=headers, json=payload)
                    response.raise_for_status()
                    return response.json()
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code not in {502, 503, 504} or attempt == 2:
                        raise
                    last_error = exc
                except httpx.TimeoutException as exc:
                    if attempt == 2:
                        raise
                    last_error = exc
                await asyncio.sleep(0.5 * (attempt + 1))
        if last_error:
            raise last_error
        msg = "OpenAI-compatible provider failed without an HTTP response."
        raise LLMProviderError(msg)


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
