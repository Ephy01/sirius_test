"""Life cycle of a task inside an attempt: lookup, generation, scoring and closing."""

from __future__ import annotations

from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .attempts import attempt_task_config
from .dependencies import api_error
from .events import append_task_event, canonical_hash
from .models import Attempt, Contest, TaskInstance, TaskStatus, as_utc, utc_now
from .routing import Route, choose_route, route_records, task_seed
from .tasks import family_for, generate_task


def active_task(session: Session, attempt_id: str) -> TaskInstance | None:
    return session.scalar(
        select(TaskInstance).where(
            TaskInstance.attempt_id == attempt_id, TaskInstance.status == TaskStatus.ACTIVE
        )
    )


def get_task_or_error(
    session: Session, attempt: Attempt, task_id: str, *, lock: bool = False
) -> TaskInstance:
    statement = select(TaskInstance).where(TaskInstance.id == task_id, TaskInstance.attempt_id == attempt.id)
    if lock:
        statement = statement.with_for_update()
    task = session.scalar(statement)
    if task is None:
        raise api_error(status.HTTP_404_NOT_FOUND, 'TASK_NOT_FOUND', 'Задача не найдена в текущей попытке.')
    return task


def get_active_task_or_error(session: Session, attempt: Attempt, task_id: str) -> TaskInstance:
    task = get_task_or_error(session, attempt, task_id)
    if task.status != TaskStatus.ACTIVE:
        raise api_error(
            status.HTTP_409_CONFLICT, 'TASK_ALREADY_CLOSED', 'Ответ на эту задачу уже зафиксирован.'
        )
    return task


def private_state_of(task: TaskInstance) -> dict:
    return task.private_state if isinstance(task.private_state, dict) else {}


def task_state_hash(task: TaskInstance) -> str:
    return canonical_hash(
        {'public_state': task.public_state, 'private_state': task.private_state, 'status': task.status.value}
    )


def first_action_latency_ms(task: TaskInstance) -> int:
    return max(0, int((utc_now() - as_utc(task.created_at)).total_seconds() * 1000))


def input_frozen_until(task: TaskInstance) -> datetime | None:
    value = private_state_of(task).get('input_frozen_until')
    if not isinstance(value, str):
        return None
    try:
        return as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def require_input_available(task: TaskInstance) -> None:
    frozen_until = input_frozen_until(task)
    now = utc_now()
    if frozen_until is None or frozen_until <= now:
        return
    remaining = max(1, int((frozen_until - now).total_seconds() + 0.999))
    raise api_error(
        status.HTTP_429_TOO_MANY_REQUESTS,
        'TASK_INPUT_FROZEN',
        f'Ввод временно приостановлен. Повторите через {remaining} с.',
    )


def director_signal(evaluation: dict, *, skipped: bool = False) -> str:
    if skipped or evaluation.get('correct') is not True:
        return 'struggle'
    return 'pass' if evaluation.get('efficient') is False else 'strong'


def scored_evaluation(task: TaskInstance, evaluation: dict) -> dict:
    """Evaluation enriched with the fields every log consumer relies on."""

    scored = dict(evaluation)
    score = scored.get('continuous_score')
    if isinstance(score, bool) or not isinstance(score, (int, float)):
        score = 1.0 if scored.get('correct') is True else 0.0
    scored['continuous_score'] = min(1.0, max(0.0, float(score)))
    scored['difficulty'] = task.difficulty
    scored['family'] = task.family
    scored['generator_version'] = task.generator_version
    if scored.get('should_finalize') is not False:
        scored['score'] = 1 if scored.get('correct') is True else 0
    return scored


def close_task(
    task: TaskInstance, status_value: TaskStatus, evaluation: dict, answer: str | None = None
) -> None:
    task.status = status_value
    task.active_slot = None
    task.evaluation_state = evaluation
    task.completed_at = utc_now()
    if answer is not None:
        task.participant_answer = answer


def _generate_states(route: Route, seed: int) -> tuple[dict, dict]:
    selected = route.selected
    family = family_for(selected.family)
    context: dict = {}
    if selected.skin is not None:
        context['skin'] = selected.skin
    if selected.sub_kinds:
        context['sub_kinds'] = list(selected.sub_kinds)
    generated = generate_task(
        family=family.key,
        generator_version=family.version,
        seed=seed,
        difficulty=route.difficulty,
        context=context,
    )
    public_state, private_state = dict(generated.public_state), dict(generated.private_state)
    if selected.skin is not None:
        public_state.setdefault('skin', selected.skin)
    return public_state, private_state


def create_or_get_current_task(
    session: Session, attempt: Attempt, contest: Contest
) -> tuple[TaskInstance, bool]:
    current = active_task(session, attempt.id)
    if current is not None:
        return current, False

    task_config = attempt_task_config(session, attempt, contest)
    latest = session.scalar(
        select(TaskInstance)
        .where(TaskInstance.attempt_id == attempt.id)
        .order_by(TaskInstance.ordinal.desc())
        .limit(1)
    )
    ordinal = (latest.ordinal if latest is not None else 0) + 1
    route = choose_route(session, attempt, task_config, ordinal, latest)
    family = family_for(route.selected.family)
    seed, context_hash = task_seed(attempt, ordinal, route, task_config)
    public_state, private_state = _generate_states(route, seed)
    private_extra, event_extra = route_records(route, context_hash, task_config)

    task = TaskInstance(
        attempt_id=attempt.id,
        ordinal=ordinal,
        family=family.key,
        generator_version=family.version,
        seed=seed,
        difficulty=route.difficulty,
        status=TaskStatus.ACTIVE,
        active_slot=True,
        public_state=public_state,
        private_state={**private_state, **private_extra},
    )
    event = {
        'ordinal': ordinal,
        'family': family.key,
        'generator_version': family.version,
        'seed': seed,
        'difficulty': route.difficulty,
        'public_state': public_state,
        'configured_weight': route.selected.weight_units / 1000 if route.scripted is None else 0,
        **event_extra,
        'family_route_version': route.version,
    }
    session.add(task)
    try:
        session.flush()
        append_task_event(session, task, 'task_generated', event)
        session.commit()
    except IntegrityError:
        session.rollback()
        current = active_task(session, attempt.id)
        if current is None:
            raise
        return current, False
    session.refresh(task)
    return task, True
