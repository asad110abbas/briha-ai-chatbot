"""Thin LLM wrapper. OpenAILLM for real use; tests inject a scripted fake with the same interface."""

from dataclasses import dataclass
from typing import Protocol, TypeVar

import httpx
import openai
from pydantic import BaseModel

from app.config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


class LLM(Protocol):
    async def parse(self, *, model: str, system: str, user: str, schema: type[T]) -> tuple[T, Usage]: ...
    async def text(self, *, model: str, system: str, user: str) -> tuple[str, Usage]: ...


class OpenAILLM:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = openai.AsyncOpenAI(
            api_key=settings.openai_api_key or "missing",
            base_url=settings.openai_base_url or None,
            timeout=30.0,
            max_retries=1,
            http_client=httpx.AsyncClient(proxy=settings.https_proxy) if settings.https_proxy else None,
        )

    def _extra(self) -> dict:
        effort = self._settings.openai_reasoning_effort
        # store=False: don't keep company data at OpenAI beyond the request.
        return {"store": False, **({"reasoning": {"effort": effort}} if effort else {})}

    def _check_key(self) -> None:
        if not self._settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is not set in .env")

    async def parse(self, *, model: str, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        self._check_key()
        try:
            r = await self._client.responses.parse(
                model=model, instructions=system, input=user, text_format=schema, **self._extra()
            )
        except openai.OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        if r.output_parsed is None:
            raise LLMError("model returned no structured output")
        return r.output_parsed, _usage(r)

    async def text(self, *, model: str, system: str, user: str) -> tuple[str, Usage]:
        self._check_key()
        try:
            r = await self._client.responses.create(model=model, instructions=system, input=user, **self._extra())
        except openai.OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        return r.output_text.strip(), _usage(r)

    async def ping(self) -> bool:
        if not self._settings.openai_api_key:
            return False
        try:
            await self._client.models.retrieve(self._settings.openai_model_understanding, timeout=5.0)
            return True
        except openai.OpenAIError:
            return False


def _usage(r) -> Usage:
    u = getattr(r, "usage", None)
    return Usage(getattr(u, "input_tokens", 0) or 0, getattr(u, "output_tokens", 0) or 0)


class GeminiLLM:
    """Google Gemini through its OpenAI-compatible endpoint (LLM_MODE=gemini). Used for testing before GPT-5.

    The same model serves all three agents; the per-agent OPENAI_MODEL_* names are ignored.
    """

    def __init__(self, settings: Settings):
        self._settings = settings
        self._model = settings.gemini_model
        self._client = openai.AsyncOpenAI(
            api_key=settings.gemini_api_key or "missing", base_url=settings.gemini_base_url, timeout=30.0,
            max_retries=3,  # free tier returns 429 often; the SDK backs off and retries
            http_client=httpx.AsyncClient(proxy=settings.https_proxy) if settings.https_proxy else None,
        )

    def _check_key(self) -> None:
        if not self._settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not set")

    async def parse(self, *, model: str, system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
        self._check_key()
        try:
            r = await self._client.chat.completions.parse(
                model=self._model, response_format=schema,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
        except (openai.OpenAIError, ValueError) as exc:
            raise LLMError(str(exc)) from exc
        parsed = r.choices[0].message.parsed
        if parsed is None:
            raise LLMError("model returned no structured output")
        return parsed, _chat_usage(r)

    async def text(self, *, model: str, system: str, user: str) -> tuple[str, Usage]:
        self._check_key()
        try:
            r = await self._client.chat.completions.create(
                model=self._model, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            )
        except openai.OpenAIError as exc:
            raise LLMError(str(exc)) from exc
        return (r.choices[0].message.content or "").strip(), _chat_usage(r)

    async def ping(self) -> bool:
        if not self._settings.gemini_api_key:
            return False
        try:
            await self._client.models.retrieve(self._model, timeout=5.0)
            return True
        except openai.OpenAIError:
            return False


def _chat_usage(r) -> Usage:
    u = getattr(r, "usage", None)
    return Usage(getattr(u, "prompt_tokens", 0) or 0, getattr(u, "completion_tokens", 0) or 0)
