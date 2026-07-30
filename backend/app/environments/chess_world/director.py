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
PENULTIMA_FAMILY = "penultima"


def decide_next_task(
    *,
    seed: int,
    families: Sequence[FamilySettings],
    history: Sequence[CompletedTask],
    start_family: str | None = None,
) -> DirectorDecision:
    """Compatibility shim for contests pinned to the Chess World v1 route."""

    legacy_families = [
        replace(
            settings,
            locked_chapter=(
                settings.locked_chapter
                or settings.family == PENULTIMA_FAMILY
            ),
        )
        for settings in families
    ]
    decision = decide_v2_next_task(
        seed=seed,
        families=legacy_families,
        history=history,
        start_family=start_family,
        version=DIRECTOR_VERSION,
    )
    legacy_reason = {
        "locked_chapter_remediation": "penultima_chapter_remediation",
        "locked_chapter_continuation": "penultima_chapter_continuation",
    }.get(decision.reason, decision.reason)
    return replace(
        decision,
        version=DIRECTOR_VERSION,
        reason=legacy_reason,
    )


__all__ = [
    "CompletedTask",
    "DIRECTOR_VERSION",
    "DirectorDecision",
    "DirectorPhase",
    "FamilySettings",
    "decide_next_task",
]
