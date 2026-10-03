"""Routing of an attempt: which family and difficulty come next, and with which seed."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .contest_config import (
    FamilyTaskSettings,
    ScriptedTaskSettings,
    adaptive_trajectory,
    family_settings,
    scripted_task,
)
from .dependencies import api_error
from .events import canonical_hash
from .models import Attempt, TaskInstance, TaskStatus, as_utc, utc_now
from .tasks import derive_task_seed, family_for
from .tasks.director import CompletedTask, DirectorDecision, DirectorPhase, FamilySettings, decide_next_task

FAMILY_ROUTE_VERSION = 'weighted-family-route-v1'
SCRIPTED_ROUTE_VERSION = 'scripted-task-route-v1'
MIN_FAMILY_EXPOSURES = 3
QUOTA_SECONDS_PER_TASK = 90


def _evidence(task: TaskInstance) -> int:
    """Adaptation signal: +1 efficient success, 0 supported success, -1 failure or skip."""

    evaluation = task.evaluation_state if isinstance(task.evaluation_state, dict) else {}
    if task.status == TaskStatus.SKIPPED or evaluation.get('correct') is not True:
        return -1
    return 0 if evaluation.get('efficient') is False else 1


def _phase(task: TaskInstance) -> DirectorPhase:
    state = task.private_state if isinstance(task.private_state, dict) else {}
    # Tasks generated before the rename keep the phase under 'world_director'.
    metadata = state.get('director') or state.get('world_director')
    try:
        return DirectorPhase(str(metadata.get('phase') if isinstance(metadata, dict) else None))
    except ValueError:
        return DirectorPhase.ROTATION


def director_history(session: Session, attempt_id: str) -> list[CompletedTask]:
    tasks = session.scalars(
        select(TaskInstance)
        .where(TaskInstance.attempt_id == attempt_id, TaskInstance.status != TaskStatus.ACTIVE)
        .order_by(TaskInstance.ordinal)
    )
    return [
        CompletedTask(
            task_id=task.id,
            family=task.family,
            difficulty=task.difficulty,
            evidence=_evidence(task),
            phase=_phase(task),
            skipped=task.status == TaskStatus.SKIPPED,
        )
        for task in tasks
    ]


def soft_quota(
    settings: list[FamilyTaskSettings], history: list[CompletedTask], deadline_at: datetime | None
) -> int | None:
    """Minimal exposures per family, while the attempt still has time for them."""

    if deadline_at is None:
        return None
    counts = {item.family: 0 for item in settings}
    for task in history:
        if task.family in counts:
            counts[task.family] += 1
    missing = sum(max(0, MIN_FAMILY_EXPOSURES - count) for count in counts.values())
    remaining_seconds = (as_utc(deadline_at) - utc_now()).total_seconds()
    if missing and remaining_seconds < missing * QUOTA_SECONDS_PER_TASK:
        return None
    return MIN_FAMILY_EXPOSURES


def weighted_family(
    attempt_seed: int, ordinal: int, settings: list[FamilyTaskSettings], exclude_family: str | None
) -> FamilyTaskSettings:
    candidates = [item for item in settings if item.family != exclude_family] or settings
    route_seed = derive_task_seed(attempt_seed, ordinal, 'family_route', FAMILY_ROUTE_VERSION)
    selection = route_seed % sum(item.weight_units for item in candidates)
    cursor = 0
    for item in candidates:
        cursor += item.weight_units
        if selection < cursor:
            return item
    raise RuntimeError('Weighted family selection did not produce a family')


def static_difficulty(session: Session, attempt_id: str, selected: FamilyTaskSettings, threshold: int) -> int:
    answered = session.scalars(
        select(TaskInstance).where(
            TaskInstance.attempt_id == attempt_id,
            TaskInstance.family == selected.family,
            TaskInstance.status == TaskStatus.ANSWERED,
        )
    )
    correct = sum(
        1
        for task in answered
        if isinstance(task.evaluation_state, dict) and task.evaluation_state.get('correct') is True
    )
    return min(selected.max_difficulty, selected.initial_difficulty + correct // threshold)


def _seed_relevant_config(config: dict) -> dict:
    """Task config without presentation-only skins, which must not change tasks."""

    normalized = json.loads(json.dumps(config))
    families = normalized.get('families')
    for family in families if isinstance(families, list) else []:
        if isinstance(family, dict):
            family.pop('skin', None)
    return normalized


def _director_context_hash(
    decision: DirectorDecision, task_config: dict, history: list[CompletedTask]
) -> str:
    # The set of keys is part of director-v2: changing it changes every generated task.
    return canonical_hash(
        {
            'version': decision.version,
            'family': decision.family,
            'difficulty': decision.difficulty,
            'phase': decision.phase.value,
            'reason': decision.reason,
            'task_config_hash': canonical_hash(_seed_relevant_config(task_config)),
            'history': [
                {
                    'family': item.family,
                    'difficulty': item.difficulty,
                    'evidence': item.evidence,
                    'skipped': item.skipped,
                    'phase': item.phase.value,
                    'chapter_stage': None,
                }
                for item in history
            ],
            'family_context_hash': None,
        }
    )


def _contextual_seed(base_seed: int, context_hash: str) -> int:
    digest = hashlib.sha256(f'{base_seed}:{context_hash}'.encode('ascii')).digest()
    return int.from_bytes(digest[:8], byteorder='big') & ((1 << 63) - 1)


@dataclass(frozen=True)
class Route:
    """The next task of an attempt and the reason it was chosen."""

    selected: FamilyTaskSettings
    difficulty: int
    scripted: ScriptedTaskSettings | None = None
    decision: DirectorDecision | None = None
    history: tuple[CompletedTask, ...] = ()

    @property
    def version(self) -> str:
        if self.scripted is not None:
            return SCRIPTED_ROUTE_VERSION
        return self.decision.version if self.decision is not None else FAMILY_ROUTE_VERSION


def _scripted_at(task_config: dict, ordinal: int) -> ScriptedTaskSettings | None:
    try:
        scripted = scripted_task(task_config)
    except ValueError as error:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'SCRIPTED_TASK_CONFIG_INVALID',
            'Сохранённая конфигурация заскриптованной задачи некорректна.',
        ) from error
    return scripted if scripted is not None and scripted.position == ordinal else None


def _scripted_route(scripted: ScriptedTaskSettings) -> Route:
    selected = FamilyTaskSettings(
        family=scripted.family,
        weight_units=0,
        initial_difficulty=1,
        max_difficulty=1,
        sub_kinds=(scripted.sub_kind,),
    )
    return Route(selected=selected, difficulty=1, scripted=scripted)


def _director_route(
    session: Session, attempt: Attempt, settings: list[FamilyTaskSettings], start_family: str | None
) -> Route:
    history = director_history(session, attempt.id)
    enabled = {item.family: item for item in settings}
    decision = decide_next_task(
        seed=attempt.seed,
        families=[
            FamilySettings(
                family=item.family,
                weight=item.weight_units,
                initial_difficulty=item.initial_difficulty,
                max_difficulty=item.max_difficulty,
            )
            for item in settings
        ],
        history=history,
        start_family=start_family if start_family in enabled else None,
        min_family_exposures=soft_quota(settings, history, attempt.deadline_at),
    )
    return Route(
        selected=enabled[decision.family],
        difficulty=decision.difficulty,
        decision=decision,
        history=tuple(history),
    )


def _static_route(
    session: Session,
    attempt: Attempt,
    settings: list[FamilyTaskSettings],
    threshold: int,
    ordinal: int,
    latest: TaskInstance | None,
) -> Route:
    exclude = latest.family if latest is not None and len(settings) > 1 else None
    selected = weighted_family(attempt.seed, ordinal, settings, exclude)
    return Route(selected=selected, difficulty=static_difficulty(session, attempt.id, selected, threshold))


def choose_route(
    session: Session, attempt: Attempt, task_config: dict, ordinal: int, latest: TaskInstance | None
) -> Route:
    settings, threshold = family_settings(task_config)
    if not settings:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'TASK_FAMILY_NOT_AVAILABLE',
            'В контесте нет ни одного доступного семейства задач.',
        )
    scripted = _scripted_at(task_config, ordinal)
    adaptive, start_family = adaptive_trajectory(task_config)
    if scripted is not None:
        return _scripted_route(scripted)
    if adaptive:
        return _director_route(session, attempt, settings, start_family)
    return _static_route(session, attempt, settings, threshold, ordinal, latest)


def task_seed(attempt: Attempt, ordinal: int, route: Route, task_config: dict) -> tuple[int, str | None]:
    """Seed of the task and, for director routes, the hash of the context it depends on."""

    family = family_for(route.selected.family)
    name = family.key if route.scripted is None else f'{family.key}:{route.scripted.sub_kind}'
    seed = derive_task_seed(attempt.seed, ordinal, name, family.version)
    if route.decision is None:
        return seed, None
    context_hash = _director_context_hash(route.decision, task_config, route.history)
    return _contextual_seed(seed, context_hash), context_hash


def route_records(route: Route, context_hash: str | None, task_config: dict) -> tuple[dict, dict]:
    """What the route adds to the private state of a task and to its ``task_generated`` event."""

    if route.scripted is not None:
        scripted = route.scripted
        private = {
            'scripted_task': {
                'route_version': SCRIPTED_ROUTE_VERSION,
                'position': scripted.position,
                'sub_kind': scripted.sub_kind,
            }
        }
        event = {
            'decision_reason': 'configured_scripted_task',
            'scripted_position': scripted.position,
            'scripted_sub_kind': scripted.sub_kind,
            'task_config_hash': canonical_hash(task_config),
        }
        return private, event
    if route.decision is None:
        return {}, {}
    decision = route.decision
    private = {
        'director': {
            'version': decision.version,
            'phase': decision.phase.value,
            'reason': decision.reason,
            'parent_task_id': decision.parent_task_id,
            'context_hash': context_hash,
        }
    }
    event = {
        'director_version': decision.version,
        'director_phase': decision.phase.value,
        'decision_reason': decision.reason,
        'parent_task_id': decision.parent_task_id,
        'director_context_hash': context_hash,
        'task_config_hash': canonical_hash(task_config),
        'branch': decision.phase.value,
    }
    return private, event
