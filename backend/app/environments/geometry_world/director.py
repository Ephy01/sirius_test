from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ..chess_world.director import (
    CompletedTask,
    DirectorDecision,
    DirectorPhase,
    FamilySettings,
    decide_next_task as decide_weighted_next_task,
)

DIRECTOR_VERSION = "geometry-world-director-v1"


def decide_next_task(
    *,
    seed: int,
    families: Sequence[FamilySettings],
    history: Sequence[CompletedTask],
    start_family: str | None = None,
) -> DirectorDecision:
    """Route Geometry World tasks with the shared deterministic MVP policy.

    Geometry families do not currently contain locked multi-task chapters, so
    they use the shared calibration, one-remediation and coverage-debt rules.
    The returned version remains world-specific for reproducible telemetry.
    """

    decision = decide_weighted_next_task(
        seed=seed,
        families=families,
        history=history,
        start_family=start_family,
    )
    return replace(decision, version=DIRECTOR_VERSION)


__all__ = [
    "CompletedTask",
    "DIRECTOR_VERSION",
    "DirectorDecision",
    "DirectorPhase",
    "FamilySettings",
    "decide_next_task",
]
