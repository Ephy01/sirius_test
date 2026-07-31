from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ..director import (
    CompletedTask,
    DirectorDecision,
    DirectorPhase,
    FamilySettings,
    decide_next_task as decide_v2_next_task,
)

DIRECTOR_VERSION = "chess-world-director-v1"


def decide_next_task(
    *,
    seed: int,
    families: Sequence[FamilySettings],
    history: Sequence[CompletedTask],
    start_family: str | None = None,
) -> DirectorDecision:
    """Compatibility shim for contests pinned to the Chess World v1 route."""

    decision = decide_v2_next_task(
        seed=seed,
        families=families,
        history=history,
        start_family=start_family,
        version=DIRECTOR_VERSION,
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
