"""
AI provider abstraction.
Supports OpenAI and Anthropic with a unified interface.
Add new providers by subclassing BaseAIProvider.
"""
from __future__ import annotations

import abc
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import anthropic
import openai
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.exceptions import AIProviderError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AIMessage:
    role: str  # "user" | "assistant" | "system"
    content: str


@dataclass
class AIResponse:
    content: str
    tokens_used: int | None = None
    model: str = ""
    provider: str = ""


# ── Base ──────────────────────────────────────────────────────────────────────
class BaseAIProvider(abc.ABC):
    """All providers must implement these two methods."""

    @abc.abstractmethod
    async def chat(
        self,
        messages: list[AIMessage],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse: ...

    @abc.abstractmethod
    async def stream_chat(
        self,
        messages: list[AIMessage],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]: ...


# ── OpenAI ────────────────────────────────────────────────────────────────────
class OpenAIProvider(BaseAIProvider):
    def __init__(self):
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model
        self.max_tokens = settings.openai_max_tokens
        self.temperature = settings.openai_temperature

    def _build_messages(
        self, messages: list[AIMessage], system_prompt: str | None
    ) -> list[dict]:
        result = []
        if system_prompt:
            result.append({"role": "system", "content": system_prompt})
        result.extend({"role": m.role, "content": m.content} for m in messages)
        return result

    @retry(
        retry=retry_if_exception_type((openai.RateLimitError, openai.APIConnectionError)),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def chat(
        self,
        messages: list[AIMessage],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=self._build_messages(messages, system_prompt),
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                **kwargs,
            )
            return AIResponse(
                content=response.choices[0].message.content or "",
                tokens_used=response.usage.total_tokens if response.usage else None,
                model=self.model,
                provider="openai",
            )
        except openai.RateLimitError as e:
            raise AIProviderError("OpenAI rate limit reached") from e
        except openai.APIError as e:
            raise AIProviderError(f"OpenAI API error: {e}") from e

    async def stream_chat(
        self,
        messages: list[AIMessage],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        try:
            async with self._client.chat.completions.stream(
                model=self.model,
                messages=self._build_messages(messages, system_prompt),
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                **kwargs,
            ) as stream:
                async for chunk in stream:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta
        except openai.APIError as e:
            raise AIProviderError(f"OpenAI stream error: {e}") from e


# ── Anthropic ─────────────────────────────────────────────────────────────────
class AnthropicProvider(BaseAIProvider):
    def __init__(self):
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model
        self.max_tokens = settings.anthropic_max_tokens

    def _build_messages(self, messages: list[AIMessage]) -> list[dict]:
        # Anthropic requires alternating user/assistant; filter out system role
        return [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

    @retry(
        retry=retry_if_exception_type(anthropic.RateLimitError),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        stop=stop_after_attempt(3),
    )
    async def chat(
        self,
        messages: list[AIMessage],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AIResponse:
        try:
            extra = {"system": system_prompt} if system_prompt else {}
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=self._build_messages(messages),
                **extra,
                **kwargs,
            )
            content = response.content[0].text if response.content else ""
            return AIResponse(
                content=content,
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                model=self.model,
                provider="anthropic",
            )
        except anthropic.RateLimitError as e:
            raise AIProviderError("Anthropic rate limit reached") from e
        except anthropic.APIError as e:
            raise AIProviderError(f"Anthropic API error: {e}") from e

    async def stream_chat(
        self,
        messages: list[AIMessage],
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncGenerator[str, None]:
        try:
            extra = {"system": system_prompt} if system_prompt else {}
            async with self._client.messages.stream(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=self._build_messages(messages),
                **extra,
                **kwargs,
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except anthropic.APIError as e:
            raise AIProviderError(f"Anthropic stream error: {e}") from e


# ── Factory ───────────────────────────────────────────────────────────────────
_providers: dict[str, BaseAIProvider] = {}


def get_ai_provider(name: str | None = None) -> BaseAIProvider:
    """
    Return a cached provider instance.
    Defaults to settings.default_ai_provider.
    """
    provider_name = name or settings.default_ai_provider
    if provider_name not in _providers:
        if provider_name == "openai":
            _providers["openai"] = OpenAIProvider()
        elif provider_name == "anthropic":
            _providers["anthropic"] = AnthropicProvider()
        else:
            raise ValueError(f"Unknown AI provider: {provider_name}")
    return _providers[provider_name]
