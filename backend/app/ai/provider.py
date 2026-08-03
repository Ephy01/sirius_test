"""Provider-agnostic contract for the participant assistant.

The service layer speaks only these DTOs; the concrete Yandex client and the
test fake both implement :class:`AssistantProvider`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

ProviderErrorCode = Literal["AI_PROVIDER_UNAVAILABLE", "AI_PROVIDER_TIMEOUT"]


class ProviderError(Exception):
    """Provider failure already mapped to an application error code.

    The message must never contain the provider response body or headers:
    those can carry secrets and are not shown to participants anyway.
    """

    def __init__(self, code: ProviderErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: ProviderErrorCode = code


@dataclass(frozen=True)
class ProviderMessage:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class ProviderRequest:
    model_uri: str
    system_prompt: str
    context_text: str
    history: tuple[ProviderMessage, ...]
    user_message: str
    max_tokens: int
    temperature: float = 0.3


@dataclass(frozen=True)
class ProviderResult:
    text: str
    provider_request_id: str | None = None
    model_version: str | None = None
    finish_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_tokens: int | None = None
    latency_ms: int | None = None


class AssistantProvider(Protocol):
    def generate(self, request: ProviderRequest) -> ProviderResult:
        ...


@dataclass
class FakeAssistantProvider:
    """In-memory provider for tests and local runs without network access.

    Keeps every received request so tests can assert on the exact context
    the model would have seen.
    """

    reply: str = "Заглушка ассистента: попробуйте сформулировать гипотезу."
    error: ProviderError | None = None
    requests: list[ProviderRequest] = field(default_factory=list)

    def generate(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return ProviderResult(
            text=self.reply,
            provider_request_id="fake-request",
            model_version="fake-model",
            finish_reason="stop",
            input_tokens=100,
            output_tokens=42,
            total_tokens=142,
            cached_tokens=0,
            latency_ms=5,
        )
