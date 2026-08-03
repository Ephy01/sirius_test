"""Orchestration of one assistant turn.

Последовательность фиксирована ТЗ: проверки → pending-запись → commit →
безопасный контекст → сетевой вызов вне транзакции → короткая транзакция
с результатом и телеметрией. Автоповторов после тайм-аута нет: провайдер
мог обработать запрос, даже если ответ не дошёл.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from fastapi import status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..dependencies import api_error
from ..config import Settings
from ..models import (
    AiTurn,
    AiTurnStatus,
    Attempt,
    AttemptEvent,
    TaskInstance,
    TaskInteraction,
    utc_now,
)
from .context import build_task_context
from .prompt import bounded_context_text, build_system_prompt, prompt_version
from .provider import (
    AssistantProvider,
    ProviderError,
    ProviderMessage,
    ProviderRequest,
)

AI_MODES = frozenset({"off", "socratic", "open"})
# A pending turn older than this is considered orphaned (process died between
# commit and completion) and no longer blocks the participant.
PENDING_STALE_SECONDS = 90
QUEUE_WAIT_SECONDS = 10

_SEMAPHORE_LOCK = threading.Lock()
_SEMAPHORES: dict[int, threading.BoundedSemaphore] = {}


@dataclass(frozen=True)
class AiConfig:
    enabled: bool = False
    mode: str = "socratic"
    max_turns_per_attempt: int = 15
    max_turns_per_task: int = 5
    max_input_characters: int = 4_000
    max_output_tokens: int = 500
    history_turns: int = 6


@dataclass(frozen=True)
class AiRemaining:
    task: int
    attempt: int


def _bounded(value: Any, default: int, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(maximum, max(minimum, value))


def parse_ai_config(raw: Any) -> AiConfig:
    if not isinstance(raw, dict):
        return AiConfig()
    mode = raw.get("mode")
    if mode not in AI_MODES:
        mode = "socratic"
    return AiConfig(
        enabled=raw.get("enabled") is True and mode != "off",
        mode=mode,
        max_turns_per_attempt=_bounded(raw.get("max_turns_per_attempt"), 15, 1, 200),
        max_turns_per_task=_bounded(raw.get("max_turns_per_task"), 5, 1, 50),
        max_input_characters=_bounded(
            raw.get("max_input_characters"), 4_000, 100, 16_000
        ),
        max_output_tokens=_bounded(raw.get("max_output_tokens"), 500, 50, 4_000),
        history_turns=_bounded(raw.get("history_turns"), 6, 0, 20),
    )


def attempt_ai_config(session: Session, attempt: Attempt) -> AiConfig:
    """Config snapshot fixed at attempt start (attempt_started event)."""

    event = session.scalar(
        select(AttemptEvent)
        .where(
            AttemptEvent.attempt_id == attempt.id,
            AttemptEvent.event_type == "attempt_started",
        )
        .order_by(AttemptEvent.sequence)
        .limit(1)
    )
    snapshot: Any = None
    if event is not None and isinstance(event.payload, dict):
        config_snapshot = event.payload.get("task_config_snapshot")
        if isinstance(config_snapshot, dict):
            snapshot = config_snapshot.get("ai")
    if snapshot is None:
        # Attempts started before the AI feature existed fall back to the
        # contest configuration (frozen semantics are impossible in hindsight).
        contest_config = attempt.enrollment.contest.task_config
        if isinstance(contest_config, dict):
            snapshot = contest_config.get("ai")
    return parse_ai_config(snapshot)


def _completed_turns(session: Session, *, attempt_id: str, task_id: str) -> tuple[int, int]:
    attempt_count = session.scalar(
        select(func.count(AiTurn.id)).where(
            AiTurn.attempt_id == attempt_id,
            AiTurn.status == AiTurnStatus.COMPLETED,
        )
    )
    task_count = session.scalar(
        select(func.count(AiTurn.id)).where(
            AiTurn.task_instance_id == task_id,
            AiTurn.status == AiTurnStatus.COMPLETED,
        )
    )
    return int(attempt_count or 0), int(task_count or 0)


def remaining_turns(
    session: Session,
    *,
    config: AiConfig,
    attempt_id: str,
    task_id: str,
) -> AiRemaining:
    attempt_used, task_used = _completed_turns(
        session, attempt_id=attempt_id, task_id=task_id
    )
    return AiRemaining(
        task=max(0, config.max_turns_per_task - task_used),
        attempt=max(0, config.max_turns_per_attempt - attempt_used),
    )


def _provider_semaphore(settings: Settings) -> threading.BoundedSemaphore:
    limit = settings.yandex_ai_max_parallel_requests
    with _SEMAPHORE_LOCK:
        semaphore = _SEMAPHORES.get(limit)
        if semaphore is None:
            semaphore = threading.BoundedSemaphore(limit)
            _SEMAPHORES[limit] = semaphore
        return semaphore


def _history_messages(
    session: Session,
    *,
    task_id: str,
    history_turns: int,
) -> tuple[ProviderMessage, ...]:
    if history_turns <= 0:
        return ()
    recent = session.scalars(
        select(AiTurn)
        .where(
            AiTurn.task_instance_id == task_id,
            AiTurn.status == AiTurnStatus.COMPLETED,
        )
        .order_by(AiTurn.sequence.desc())
        .limit(history_turns)
    ).all()
    messages: list[ProviderMessage] = []
    for turn in reversed(recent):
        messages.append(ProviderMessage(role="user", content=turn.user_message))
        if turn.assistant_message:
            messages.append(
                ProviderMessage(role="assistant", content=turn.assistant_message)
            )
    return tuple(messages)


def _next_turn_sequence(session: Session, task_id: str) -> int:
    stored = session.scalar(
        select(func.max(AiTurn.sequence)).where(AiTurn.task_instance_id == task_id)
    )
    return int(stored or 0) + 1


def _append_ai_event(
    session: Session,
    *,
    attempt: Attempt,
    task: TaskInstance,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    # Local import breaks the api ↔ service import cycle.
    from ..api import _append_event

    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type=event_type,
        payload=payload,
    )


def run_ai_turn(
    session: Session,
    *,
    settings: Settings,
    provider: AssistantProvider | None,
    attempt: Attempt,
    task: TaskInstance,
    client_action_id: str,
    message: str,
) -> tuple[AiTurn, AiRemaining]:
    if provider is None or not settings.ai_enabled:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_NOT_CONFIGURED",
            "Ассистент временно недоступен.",
        )
    config = attempt_ai_config(session, attempt)
    if not config.enabled:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "AI_DISABLED",
            "ИИ-ассистент отключён для этого контеста.",
        )

    stripped = message.strip()
    if not stripped:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "AI_MESSAGE_EMPTY",
            "Введите сообщение.",
        )
    if len(stripped) > config.max_input_characters:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "AI_MESSAGE_TOO_LONG",
            "Сообщение слишком длинное.",
        )

    # Идемпотентность: повтор client_action_id возвращает прежний результат.
    existing = session.scalar(
        select(AiTurn).where(
            AiTurn.attempt_id == attempt.id,
            AiTurn.client_action_id == client_action_id,
        )
    )
    if existing is not None:
        remaining = remaining_turns(
            session, config=config, attempt_id=attempt.id, task_id=task.id
        )
        return existing, remaining

    pending = session.scalar(
        select(AiTurn).where(
            AiTurn.attempt_id == attempt.id,
            AiTurn.status == AiTurnStatus.PENDING,
        )
    )
    if pending is not None:
        stale_before = utc_now() - timedelta(seconds=PENDING_STALE_SECONDS)
        created_at = pending.created_at
        if created_at.tzinfo is None:
            from datetime import timezone

            created_at = created_at.replace(tzinfo=timezone.utc)
        if created_at > stale_before:
            raise api_error(
                status.HTTP_409_CONFLICT,
                "AI_TURN_IN_PROGRESS",
                "Дождитесь предыдущего ответа.",
            )
        pending.status = AiTurnStatus.FAILED
        pending.error_code = "AI_TURN_ORPHANED"
        pending.completed_at = utc_now()

    remaining = remaining_turns(
        session, config=config, attempt_id=attempt.id, task_id=task.id
    )
    if remaining.task <= 0 or remaining.attempt <= 0:
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "AI_TURN_LIMIT_REACHED",
            "Лимит обращений исчерпан.",
        )

    interactions = session.scalars(
        select(TaskInteraction)
        .where(TaskInteraction.task_instance_id == task.id)
        .order_by(TaskInteraction.sequence)
    ).all()
    context = build_task_context(task, list(interactions))
    history = _history_messages(
        session, task_id=task.id, history_turns=config.history_turns
    )
    model_uri = settings.yandex_ai_model_uri or "unconfigured"

    turn = AiTurn(
        attempt_id=attempt.id,
        task_instance_id=task.id,
        sequence=_next_turn_sequence(session, task.id),
        client_action_id=client_action_id,
        status=AiTurnStatus.PENDING,
        user_message=stripped,
        provider="yandex",
        model_uri=model_uri,
        prompt_version=prompt_version(config.mode),
        public_context_hash=context.sha256,
    )
    session.add(turn)
    _append_ai_event(
        session,
        attempt=attempt,
        task=task,
        event_type="ai_turn_requested",
        payload={
            "aiTurnId": turn.id,
            "inputLength": len(stripped),
            "contextHash": context.sha256,
            "promptVersion": turn.prompt_version,
        },
    )
    session.commit()

    request = ProviderRequest(
        model_uri=model_uri,
        system_prompt=build_system_prompt(config.mode),
        context_text=bounded_context_text(context.canonical_json),
        history=history,
        user_message=stripped,
        max_tokens=config.max_output_tokens,
    )

    semaphore = _provider_semaphore(settings)
    if not semaphore.acquire(timeout=QUEUE_WAIT_SECONDS):
        _finish_turn_failed(session, attempt, task, turn, "AI_BUSY")
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "AI_BUSY",
            "Ассистент занят, попробуйте через несколько секунд.",
        )
    try:
        # Сетевой вызов — вне какой-либо транзакции БД (предыдущий commit
        # закрыл её; следующая начнётся лениво при записи результата).
        result = provider.generate(request)
    except ProviderError as error:
        semaphore.release()
        _finish_turn_failed(session, attempt, task, turn, error.code)
        http_status = (
            status.HTTP_504_GATEWAY_TIMEOUT
            if error.code == "AI_PROVIDER_TIMEOUT"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        messages = {
            "AI_PROVIDER_TIMEOUT": "Ассистент не успел ответить.",
            "AI_PROVIDER_UNAVAILABLE": "Не удалось связаться с ассистентом.",
        }
        raise api_error(http_status, error.code, messages[error.code])
    else:
        semaphore.release()

    turn.status = AiTurnStatus.COMPLETED
    turn.assistant_message = result.text
    turn.model_version = result.model_version
    turn.provider_request_id = result.provider_request_id
    turn.finish_reason = result.finish_reason
    turn.input_tokens = result.input_tokens
    turn.output_tokens = result.output_tokens
    turn.total_tokens = result.total_tokens
    turn.cached_tokens = result.cached_tokens
    turn.latency_ms = result.latency_ms
    turn.completed_at = utc_now()
    _append_ai_event(
        session,
        attempt=attempt,
        task=task,
        event_type="ai_turn_completed",
        payload={
            "aiTurnId": turn.id,
            "taskId": task.id,
            "model": result.model_version or model_uri,
            "latencyMs": result.latency_ms,
            "inputTokens": result.input_tokens,
            "outputTokens": result.output_tokens,
            "finishReason": result.finish_reason,
        },
    )
    session.commit()
    session.refresh(turn)
    remaining = remaining_turns(
        session, config=config, attempt_id=attempt.id, task_id=task.id
    )
    return turn, remaining


def _finish_turn_failed(
    session: Session,
    attempt: Attempt,
    task: TaskInstance,
    turn: AiTurn,
    error_code: str,
) -> None:
    turn.status = AiTurnStatus.FAILED
    turn.error_code = error_code
    turn.completed_at = utc_now()
    _append_ai_event(
        session,
        attempt=attempt,
        task=task,
        event_type="ai_turn_failed",
        payload={"aiTurnId": turn.id, "errorCode": error_code},
    )
    session.commit()
