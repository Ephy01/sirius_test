from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

DIRECTOR_VERSION = 'director-v2'


class DirectorPhase(StrEnum):
    CALIBRATION = 'calibration'
    REMEDIATION = 'remediation'
    ROTATION = 'rotation'


@dataclass(frozen=True)
class FamilySettings:
    """Organizer-controlled bounds and routing policy for one task family."""

    family: str
    weight: int = 1
    initial_difficulty: int = 1
    max_difficulty: int = 5
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.family.strip():
            raise ValueError('family must not be empty')
        if self.weight < 0:
            raise ValueError('weight must not be negative')
        if self.initial_difficulty < 1:
            raise ValueError('initial_difficulty must be at least 1')
        if self.max_difficulty < self.initial_difficulty:
            raise ValueError('max_difficulty must be greater than or equal to initial_difficulty')


@dataclass(frozen=True)
class CompletedTask:
    """Minimal, storage-agnostic history consumed by the director.

    ``evidence`` is an operational adaptation signal:

    * ``+1`` — an independent, efficient success;
    * ``0`` — a supported or noisy success;
    * ``-1`` — an incorrect answer or a skip.

    ``skipped`` keeps those two cases distinct for routing: an incorrect
    answer may receive remediation, while a deliberate skip should expose the
    participant to another enabled family whenever possible.

    History must be passed from oldest to newest.
    """

    task_id: str
    family: str
    difficulty: int
    evidence: int
    phase: DirectorPhase = DirectorPhase.ROTATION
    skipped: bool = False

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError('task_id must not be empty')
        if not self.family:
            raise ValueError('family must not be empty')
        if self.difficulty < 1:
            raise ValueError('difficulty must be at least 1')
        if self.evidence not in (-1, 0, 1):
            raise ValueError('evidence must be one of -1, 0, or 1')
        if self.skipped and self.evidence != -1:
            raise ValueError('a skipped task must have evidence -1')


@dataclass(frozen=True)
class DirectorDecision:
    family: str
    difficulty: int
    reason: str
    phase: DirectorPhase
    version: str
    parent_task_id: str | None


def _stable_rank(*, seed: int, phase: str, family: str, turn: int, version: str) -> int:
    payload = f'{version}:{seed}:{phase}:{turn}:{family}'.encode()
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], byteorder='big')


def _active_settings(families: Sequence[FamilySettings]) -> dict[str, FamilySettings]:
    active: dict[str, FamilySettings] = {}
    for settings in families:
        if not settings.enabled or settings.weight == 0:
            continue
        if settings.family in active:
            raise ValueError(f'duplicate family settings: {settings.family}')
        active[settings.family] = settings
    if not active:
        raise ValueError('at least one enabled family with positive weight is required')
    return active


def _history_for_family(history: Sequence[CompletedTask], family: str) -> list[CompletedTask]:
    return [task for task in history if task.family == family]


def _difficulty_for(settings: FamilySettings, history: Sequence[CompletedTask]) -> int:
    family_history = _history_for_family(history, settings.family)
    if not family_history:
        return settings.initial_difficulty

    latest_raw_level = family_history[-1].difficulty
    current_level = min(settings.max_difficulty, max(1, latest_raw_level))

    same_level_suffix: list[CompletedTask] = []
    for task in reversed(family_history):
        if task.difficulty != latest_raw_level:
            break
        same_level_suffix.append(task)
        if len(same_level_suffix) == 3:
            break

    if len(same_level_suffix) < 3:
        return current_level

    evidence_sum = sum(task.evidence for task in same_level_suffix)
    if evidence_sum >= 2:
        return min(settings.max_difficulty, current_level + 1)
    if evidence_sum <= -2:
        return max(1, current_level - 1)
    return current_level


def _latest_parent(history: Sequence[CompletedTask], family: str) -> str | None:
    for task in reversed(history):
        if task.family == family:
            return task.task_id
    return None


def _decision(
    *,
    settings: FamilySettings,
    history: Sequence[CompletedTask],
    phase: DirectorPhase,
    reason: str,
    parent_task_id: str | None,
) -> DirectorDecision:
    return DirectorDecision(
        family=settings.family,
        difficulty=_difficulty_for(settings, history),
        reason=reason,
        phase=phase,
        version=DIRECTOR_VERSION,
        parent_task_id=parent_task_id,
    )


def decide_next_task(
    *,
    seed: int,
    families: Sequence[FamilySettings],
    history: Sequence[CompletedTask],
    start_family: str | None = None,
    min_family_exposures: int | None = None,
) -> DirectorDecision:
    """Choose the next task from completed-task history.

    Precedence is intentional:

    1. when several families are enabled, the latest family is never selected
       twice in a row, regardless of whether the task was answered or skipped;
    2. with a single enabled family, an incorrect answer may receive one
       remediation task;
    3. every enabled family receives a seeded calibration task;
    4. later tasks follow weighted coverage debt while preserving the
       no-consecutive-family invariant.

    ``min_family_exposures`` is the learning-slope soft quota: while any
    active family has fewer exposures, rotation prefers those families
    (still ordered by coverage debt). The caller enables it only when the
    attempt has enough remaining time, so it is an operational signal —
    like remediation — rather than part of the versioned route identity.
    """

    active = _active_settings(families)
    relevant_history = [task for task in history if task.family in active]
    latest = relevant_history[-1] if relevant_history else None

    if not relevant_history and start_family in active:
        return _decision(
            settings=active[start_family],
            history=relevant_history,
            phase=DirectorPhase.CALIBRATION,
            reason='configured_start_family',
            parent_task_id=None,
        )

    if (
        latest is not None
        and len(active) == 1
        and latest.evidence == -1
        and not latest.skipped
        and latest.phase != DirectorPhase.REMEDIATION
    ):
        return _decision(
            settings=active[latest.family],
            history=relevant_history,
            phase=DirectorPhase.REMEDIATION,
            reason='failed_or_skipped_task_remediation',
            parent_task_id=latest.task_id,
        )

    completed_families = {task.family for task in relevant_history}
    missing_families = [settings for family, settings in active.items() if family not in completed_families]
    if missing_families:
        selected = min(
            missing_families,
            key=lambda item: (
                _stable_rank(
                    seed=seed,
                    phase=DirectorPhase.CALIBRATION,
                    family=item.family,
                    turn=0,
                    version=DIRECTOR_VERSION,
                ),
                item.family,
            ),
        )
        return _decision(
            settings=selected,
            history=relevant_history,
            phase=DirectorPhase.CALIBRATION,
            reason='seeded_family_calibration',
            parent_task_id=None,
        )

    counts = {family: len(_history_for_family(relevant_history, family)) for family in active}
    total_completed = sum(counts.values())
    total_weight = sum(settings.weight for settings in active.values())

    debt_numerators = {
        family: (total_completed + 1) * settings.weight - counts[family] * total_weight
        for family, settings in active.items()
    }
    capped_remediation = (
        latest is not None and latest.evidence == -1 and latest.phase == DirectorPhase.REMEDIATION
    )
    avoid_latest_family = latest is not None and len(active) > 1
    route_candidates = [
        family
        for family in active
        if not (avoid_latest_family and latest is not None and family == latest.family)
    ]
    quota_applied = False
    if min_family_exposures is not None and min_family_exposures > 0:
        under_quota = [family for family in route_candidates if counts[family] < min_family_exposures]
        if under_quota and len(under_quota) < len(route_candidates):
            route_candidates = under_quota
            quota_applied = True
    selected_family = min(
        route_candidates,
        key=lambda family: (
            -debt_numerators[family],
            _stable_rank(
                seed=seed,
                phase=DirectorPhase.ROTATION,
                family=family,
                turn=total_completed,
                version=DIRECTOR_VERSION,
            ),
            family,
        ),
    )
    return _decision(
        settings=active[selected_family],
        history=relevant_history,
        phase=DirectorPhase.ROTATION,
        reason=(
            'skipped_task_diversity_rotation'
            if latest is not None and latest.skipped and avoid_latest_family
            else 'failed_task_diversity_rotation'
            if (
                latest is not None
                and latest.evidence == -1
                and avoid_latest_family
                and not capped_remediation
            )
            else 'remediation_cap_weighted_rotation'
            if capped_remediation
            else 'soft_exposure_quota'
            if quota_applied
            else 'weighted_coverage_debt'
        ),
        parent_task_id=_latest_parent(relevant_history, selected_family),
    )
