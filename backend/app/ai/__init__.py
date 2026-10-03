"""Participant assistant: visible context, prompts, limits and the model provider."""

from .context import build_task_context
from .provider import (
    AssistantProvider,
    FakeAssistantProvider,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
    ProviderResult,
)
from .report import generate_telemetry_markdown
from .service import AiRemaining, attempt_ai_config, remaining_turns, run_ai_turn
from .tripwire import CRISIS_CATEGORY, crisis_category
from .yandex import provider_from_settings

__all__ = [
    'AiRemaining',
    'AssistantProvider',
    'CRISIS_CATEGORY',
    'FakeAssistantProvider',
    'ProviderError',
    'ProviderMessage',
    'ProviderRequest',
    'ProviderResult',
    'attempt_ai_config',
    'build_task_context',
    'crisis_category',
    'generate_telemetry_markdown',
    'provider_from_settings',
    'remaining_turns',
    'run_ai_turn',
]
