from datetime import timedelta

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..attempts import require_active_attempt, task_config_of
from ..dependencies import ParticipantEnrollmentDependency, SessionDependency, api_error
from ..events import append_task_event
from ..models import TaskInstance, TaskInteraction, TaskStatus, utc_now
from ..schemas import (
    DebugAnswerResponse,
    TaskActionResponse,
    TaskAnswerRequest,
    TaskInteractionRequest,
    TaskInteractionResponse,
)
from ..task_flow import (
    close_task,
    director_signal,
    first_action_latency_ms,
    get_active_task_or_error,
    get_task_or_error,
    private_state_of,
    require_input_available,
    scored_evaluation,
    task_state_hash,
)
from ..tasks import FAMILIES, TaskFamily, Transition, evaluate_task, interact_task

router = APIRouter(prefix='/participant/tasks/{task_id}')

NO_REFERENCE_ANSWER = 'Эталонный ответ для этого семейства недоступен.'


def _stored_interaction(session: Session, task_id: str, client_action_id: str) -> TaskInteraction | None:
    return session.scalar(
        select(TaskInteraction).where(
            TaskInteraction.task_instance_id == task_id, TaskInteraction.client_action_id == client_action_id
        )
    )


def _replayed_response(
    task: TaskInstance, interaction: TaskInteraction, action_type: str, request: dict
) -> TaskInteractionResponse:
    """Answer a repeated request with the stored outcome of the first one."""

    if interaction.action_type != action_type or interaction.request_payload != request:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'INTERACTION_ID_REUSED',
            'Этот идентификатор действия уже использован с другими данными.',
        )
    result = interaction.result_payload if isinstance(interaction.result_payload, dict) else {}
    return TaskInteractionResponse(
        task=task,
        accepted=result.get('accepted') is True,
        completed=result.get('completed') is True,
        message=str(result.get('message') or 'Действие уже было обработано.'),
        client_action_id=interaction.client_action_id,
    )


def _action_request(payload: TaskInteractionRequest) -> dict:
    """The part of an interaction request that identifies the action."""

    if payload.action_type == 'probe':
        return {'probe': payload.probe}
    if payload.action_type == 'apply_op':
        return {'op_id': payload.op_id}
    return {}


def _require_action(task: TaskInstance, action: str) -> TaskFamily:
    if task.status != TaskStatus.ACTIVE:
        raise api_error(status.HTTP_409_CONFLICT, 'TASK_ALREADY_CLOSED', 'Эта задача уже завершена.')
    require_input_available(task)
    family = FAMILIES.get(task.family)
    if family is None or not family.actions:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'TASK_INTERACTION_NOT_SUPPORTED',
            'Для этой задачи пошаговые действия не поддерживаются.',
        )
    if action not in family.actions:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'TASK_INTERACTION_ACTION_NOT_SUPPORTED',
            'Эта команда не поддерживается текущей задачей.',
        )
    return family


def _apply_transition(task: TaskInstance, transition: Transition) -> str | None:
    """Store the new task state; returns the director signal if the action closed the task."""

    task.public_state = transition.public_state
    task.private_state = transition.private_state
    if not transition.completed:
        return None
    evaluation = scored_evaluation(task, dict(transition.evaluation_state or {}))
    evaluation['director_signal'] = director_signal(evaluation)
    close_task(task, TaskStatus.ANSWERED, evaluation, answer=transition.normalized_input)
    return evaluation['director_signal']


def _record_interaction(
    session: Session,
    task: TaskInstance,
    client_action_id: str,
    action: str,
    request: dict,
    transition: Transition,
) -> TaskInteraction:
    sequence = session.scalar(
        select(func.max(TaskInteraction.sequence)).where(TaskInteraction.task_instance_id == task.id)
    )
    interaction = TaskInteraction(
        task_instance_id=task.id,
        sequence=(sequence or 0) + 1,
        client_action_id=client_action_id,
        action_type=action,
        request_payload=request,
        result_payload={
            'accepted': transition.accepted,
            'completed': transition.completed,
            'reason': transition.reason,
            'message': transition.message,
            'normalized_input': transition.normalized_input,
        },
    )
    session.add(interaction)
    session.flush()
    return interaction


def _log_interaction(
    session: Session,
    task: TaskInstance,
    family: TaskFamily,
    interaction: TaskInteraction,
    transition: Transition,
    signal: str | None,
    hash_before: str,
) -> None:
    action = interaction.action_type
    reference = {'interaction_id': interaction.id, 'client_action_id': interaction.client_action_id}
    measurement = transition.evaluation_state if transition.accepted else None
    append_task_event(
        session,
        task,
        'task_interaction_submitted',
        {**reference, 'action_type': action, **interaction.request_payload},
    )
    append_task_event(
        session,
        task,
        'task_interaction_resolved',
        {
            **reference,
            'accepted': transition.accepted,
            'completed': transition.completed,
            'reason': transition.reason,
            'director_signal': signal,
            'before_state_hash': hash_before,
            'after_state_hash': task_state_hash(task),
        },
    )
    if isinstance(measurement, dict) and family.probe_action == action and 'gain_bits_actual' in measurement:
        append_task_event(
            session, task, 'zendo_probe', {**reference, 'card_id': transition.normalized_input, **measurement}
        )
    if isinstance(measurement, dict) and action == 'hint':
        append_task_event(session, task, 'prompt_used', {**reference, 'family': task.family, **measurement})
    if transition.completed:
        append_task_event(session, task, 'answer_evaluated', task.evaluation_state)


@router.post('/interactions', response_model=TaskInteractionResponse)
def interact_with_task(
    task_id: str,
    payload: TaskInteractionRequest,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> TaskInteractionResponse:
    attempt = require_active_attempt(session, enrollment)
    task = get_task_or_error(session, attempt, task_id, lock=True)
    action, request = payload.action_type, _action_request(payload)
    existing = _stored_interaction(session, task.id, payload.client_action_id)
    if existing is not None:
        return _replayed_response(task, existing, action, request)

    family = _require_action(task, action)
    hash_before = task_state_hash(task)
    transition = interact_task(
        family=task.family,
        generator_version=task.generator_version,
        action_type=action,
        action_payload={
            **request,
            'client_action_id': payload.client_action_id,
            'first_action_latency_ms': first_action_latency_ms(task),
        },
        public_state=task.public_state,
        private_state=task.private_state,
    )
    signal = _apply_transition(task, transition)
    interaction = _record_interaction(session, task, payload.client_action_id, action, request, transition)
    _log_interaction(session, task, family, interaction, transition, signal, hash_before)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = _stored_interaction(session, task_id, payload.client_action_id)
        stored_task = session.get(TaskInstance, task_id)
        if existing is None or stored_task is None:
            raise
        return _replayed_response(stored_task, existing, action, request)
    session.refresh(task)
    return TaskInteractionResponse(
        task=task,
        accepted=transition.accepted,
        completed=transition.completed,
        message=transition.message,
        client_action_id=payload.client_action_id,
    )


@router.get('/debug-answer', response_model=DebugAnswerResponse)
def get_debug_answer(
    task_id: str, enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> DebugAnswerResponse:
    """Reference answer for organizers testing a contest in debug mode."""

    attempt = require_active_attempt(session, enrollment)
    if task_config_of(enrollment.contest).get('debug_reveal_answers') is not True:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            'DEBUG_ANSWERS_DISABLED',
            'Команда /get answer не включена организатором этого контеста.',
        )
    task = get_active_task_or_error(session, attempt, task_id)
    family = FAMILIES.get(task.family)
    private_state = private_state_of(task)
    answer, commands = NO_REFERENCE_ANSWER, []
    if family is not None and family.reference_answer is not None:
        answer, commands = family.reference_answer(private_state)
    details = family.debug_details(private_state) if family is not None and family.debug_details else []
    append_task_event(session, task, 'debug_answer_revealed', {'family': task.family})
    session.commit()
    return DebugAnswerResponse(family=task.family, answer=answer, commands=commands, details=details)


def _track_first_action(task: TaskInstance) -> None:
    """Store how long the participant took before the first action, for families that measure it."""

    family = FAMILIES.get(task.family)
    if family is None or not family.tracks_first_action:
        return
    private_state = dict(private_state_of(task))
    interaction = dict(private_state.get('interaction') or {})
    if interaction.get('first_action_latency_ms') is not None:
        return
    interaction['first_action_latency_ms'] = first_action_latency_ms(task)
    private_state['interaction'] = interaction
    task.private_state = private_state


def _evaluate_answer(task: TaskInstance, answer: str) -> dict:
    evaluation = scored_evaluation(
        task,
        dict(
            evaluate_task(
                family=task.family,
                generator_version=task.generator_version,
                answer=answer,
                private_state=task.private_state,
            )
        ),
    )
    evaluation['director_signal'] = director_signal(evaluation)
    return evaluation


def _freeze_input(session: Session, task: TaskInstance, evaluation: dict) -> None:
    """Block further input for the time a non-final answer asks for, if it asks at all."""

    seconds = evaluation.get('freeze_seconds')
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds <= 0:
        return
    frozen_until = (utc_now() + timedelta(seconds=seconds)).isoformat()
    task.private_state = {**private_state_of(task), 'input_frozen_until': frozen_until}
    evaluation['input_frozen_until'] = frozen_until
    append_task_event(
        session,
        task,
        'task_input_frozen',
        {'seconds': seconds, 'until': frozen_until, 'reason': evaluation.get('reason')},
    )


@router.post('/answer', response_model=TaskActionResponse)
def answer_task(
    task_id: str,
    payload: TaskAnswerRequest,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> TaskActionResponse:
    attempt = require_active_attempt(session, enrollment)
    task = get_task_or_error(session, attempt, task_id)
    if task.status == TaskStatus.ANSWERED and task.participant_answer == payload.answer:
        return TaskActionResponse(
            task=task, message='Ответ уже был зафиксирован. Можно перейти к следующей задаче.'
        )
    if task.status != TaskStatus.ACTIVE:
        raise api_error(
            status.HTTP_409_CONFLICT, 'TASK_ALREADY_CLOSED', 'Ответ на эту задачу уже зафиксирован.'
        )
    require_input_available(task)

    _track_first_action(task)
    evaluation = _evaluate_answer(task, payload.answer)
    append_task_event(session, task, 'answer_submitted', {'answer': payload.answer})
    if evaluation.get('should_finalize') is False:
        _freeze_input(session, task, evaluation)
        message = str(evaluation.get('feedback') or 'Ответ пока не завершает задачу.')
    else:
        close_task(task, TaskStatus.ANSWERED, evaluation, answer=payload.answer)
        message = 'Ответ зафиксирован. Можно перейти к следующей задаче.'
    append_task_event(session, task, 'answer_evaluated', evaluation)
    session.commit()
    session.refresh(task)
    return TaskActionResponse(task=task, message=message)


@router.post('/skip', response_model=TaskActionResponse)
def skip_task(
    task_id: str, enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> TaskActionResponse:
    attempt = require_active_attempt(session, enrollment)
    task = get_task_or_error(session, attempt, task_id)
    if task.status == TaskStatus.SKIPPED:
        return TaskActionResponse(
            task=task, message='Пропуск уже был зафиксирован. Можно перейти к следующей задаче.'
        )
    if task.status != TaskStatus.ACTIVE:
        raise api_error(
            status.HTTP_409_CONFLICT, 'TASK_ALREADY_CLOSED', 'Ответ на эту задачу уже зафиксирован.'
        )
    evaluation = scored_evaluation(task, {'correct': False, 'skipped': True, 'director_signal': 'struggle'})
    close_task(task, TaskStatus.SKIPPED, evaluation)
    append_task_event(session, task, 'task_skipped', dict(evaluation))
    session.commit()
    session.refresh(task)
    return TaskActionResponse(task=task, message='Задача пропущена. Можно перейти к следующей.')
