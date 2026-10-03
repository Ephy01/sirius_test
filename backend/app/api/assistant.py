from fastapi import APIRouter, status
from sqlalchemy import select

from ..ai import AiRemaining, attempt_ai_config, remaining_turns, run_ai_turn
from ..attempts import require_active_attempt
from ..dependencies import (
    AiProviderDependency,
    ParticipantEnrollmentDependency,
    SessionDependency,
    SettingsDependency,
    api_error,
)
from ..models import AiTurn, AiTurnStatus
from ..schemas import (
    AiTurnHistoryItem,
    AiTurnHistoryResponse,
    AiTurnRemaining,
    AiTurnRequest,
    AiTurnResponse,
    AiTurnUsage,
)
from ..task_flow import get_active_task_or_error, get_task_or_error

router = APIRouter(prefix='/participant/tasks/{task_id}/ai')


def remaining_response(remaining: AiRemaining) -> AiTurnRemaining:
    return AiTurnRemaining(task=remaining.task, attempt=remaining.attempt)


@router.post('/turns', response_model=AiTurnResponse)
def create_ai_turn(
    task_id: str,
    payload: AiTurnRequest,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
    settings: SettingsDependency,
    ai_provider: AiProviderDependency,
) -> AiTurnResponse:
    attempt = require_active_attempt(session, enrollment)
    task = get_active_task_or_error(session, attempt, task_id)
    turn, remaining = run_ai_turn(
        session,
        settings=settings,
        provider=ai_provider,
        attempt=attempt,
        task=task,
        client_action_id=payload.client_action_id,
        message=payload.message,
    )
    return AiTurnResponse(
        id=turn.id,
        status=turn.status.value,
        assistant_message=turn.assistant_message,
        model=turn.model_uri,
        usage=AiTurnUsage(
            input_tokens=turn.input_tokens, output_tokens=turn.output_tokens, total_tokens=turn.total_tokens
        ),
        remaining=remaining_response(remaining),
    )


@router.get('/turns', response_model=AiTurnHistoryResponse)
def list_ai_turns(
    task_id: str, enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> AiTurnHistoryResponse:
    """Dialogue of one task, used to restore the chat after a page reload."""

    attempt = require_active_attempt(session, enrollment)
    task = get_task_or_error(session, attempt, task_id)
    config = attempt_ai_config(session, attempt)
    if not config.enabled:
        raise api_error(status.HTTP_403_FORBIDDEN, 'AI_DISABLED', 'ИИ-ассистент отключён для этого контеста.')
    turns = session.scalars(
        select(AiTurn)
        .where(AiTurn.task_instance_id == task.id, AiTurn.status == AiTurnStatus.COMPLETED)
        .order_by(AiTurn.sequence)
    ).all()
    remaining = remaining_turns(session, config=config, attempt_id=attempt.id, task_id=task.id)
    return AiTurnHistoryResponse(
        turns=[
            AiTurnHistoryItem(
                id=turn.id,
                status=turn.status.value,
                user_message=turn.user_message,
                assistant_message=turn.assistant_message,
                created_at=turn.created_at,
                completed_at=turn.completed_at,
            )
            for turn in turns
        ],
        remaining=remaining_response(remaining),
    )
