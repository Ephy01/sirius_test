from __future__ import annotations

from app.environments.chess_world.director import (
    DIRECTOR_VERSION,
    CompletedTask,
    DirectorPhase,
    FamilySettings,
    decide_next_task,
)


FAMILIES = (
    FamilySettings(family="dice_chess", weight=1, max_difficulty=5),
    FamilySettings(family="machine_reach", weight=2, max_difficulty=5),
    FamilySettings(
        family="geo_zendo",
        weight=1,
        max_difficulty=5,
        locked_chapter=True,
    ),
)


def test_decision_is_deterministic_for_seed_and_history() -> None:
    history = (
        CompletedTask(
            task_id="task-1",
            family="dice_chess",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
    )

    first = decide_next_task(seed=1042, families=FAMILIES, history=history)
    second = decide_next_task(seed=1042, families=FAMILIES, history=history)

    assert first == second
    assert first.version == DIRECTOR_VERSION


def test_seeded_calibration_covers_every_enabled_family_once() -> None:
    history: list[CompletedTask] = []
    selected: list[str] = []

    for ordinal in range(1, len(FAMILIES) + 1):
        decision = decide_next_task(
            seed=9191,
            families=FAMILIES,
            history=history,
        )
        selected.append(decision.family)
        assert decision.phase == DirectorPhase.CALIBRATION
        history.append(
            CompletedTask(
                task_id=f"task-{ordinal}",
                family=decision.family,
                difficulty=decision.difficulty,
                evidence=1,
                phase=decision.phase,
                # A calibration task represents a complete miniature chapter.
                chapter_stage=3 if decision.family == "geo_zendo" else None,
            )
        )

    assert set(selected) == {settings.family for settings in FAMILIES}
    assert len(selected) == len(set(selected))


def test_configured_start_family_is_used_before_seeded_calibration() -> None:
    first = decide_next_task(
        seed=9191,
        families=FAMILIES,
        history=(),
        start_family="machine_reach",
    )

    assert first.family == "machine_reach"
    assert first.phase == DirectorPhase.CALIBRATION
    assert first.reason == "configured_start_family"


def test_locked_chapter_interleaves_when_another_family_is_available() -> None:
    history = (
        CompletedTask(
            task_id="chapter-stage-2",
            family="geo_zendo",
            difficulty=3,
            evidence=1,
            phase=DirectorPhase.CHAPTER,
            chapter_stage=2,
        ),
    )

    decision = decide_next_task(seed=7, families=FAMILIES, history=history)

    assert decision.family != "geo_zendo"
    assert decision.phase == DirectorPhase.CALIBRATION


def test_locked_chapter_can_continue_when_it_is_the_only_family() -> None:
    family = (
        FamilySettings(
            family="geo_zendo",
            max_difficulty=5,
            locked_chapter=True,
        ),
    )
    history = (
        CompletedTask(
            task_id="chapter-stage-2",
            family="geo_zendo",
            difficulty=3,
            evidence=1,
            phase=DirectorPhase.CHAPTER,
            chapter_stage=2,
        ),
    )

    decision = decide_next_task(seed=7, families=family, history=history)

    assert decision.family == "geo_zendo"
    assert decision.difficulty == 3
    assert decision.phase == DirectorPhase.CHAPTER
    assert decision.reason == "locked_chapter_continuation"
    assert decision.parent_task_id == "chapter-stage-2"


def test_failure_rotates_before_the_family_can_return() -> None:
    families = (
        FamilySettings(family="dice_chess"),
        FamilySettings(family="machine_reach"),
    )
    history = [
        CompletedTask(
            task_id="dice-calibration",
            family="dice_chess",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="machine-calibration",
            family="machine_reach",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="dice-failure",
            family="dice_chess",
            difficulty=1,
            evidence=-1,
            phase=DirectorPhase.ROTATION,
        ),
    ]

    rotated = decide_next_task(seed=88, families=families, history=history)
    assert rotated.family == "machine_reach"
    assert rotated.phase == DirectorPhase.ROTATION
    assert rotated.reason == "failed_task_diversity_rotation"
    assert rotated.parent_task_id == "machine-calibration"

    history.append(
        CompletedTask(
            task_id="machine-after-failure",
            family=rotated.family,
            difficulty=rotated.difficulty,
            evidence=1,
            phase=rotated.phase,
        )
    )
    returned = decide_next_task(
        seed=88,
        families=families,
        history=history,
    )

    assert returned.phase == DirectorPhase.ROTATION
    assert returned.family == "dice_chess"
    assert returned.parent_task_id == "dice-failure"


def test_skip_immediately_rotates_to_a_different_family() -> None:
    families = (
        FamilySettings(family="dice_chess"),
        FamilySettings(family="machine_reach"),
    )
    history = (
        CompletedTask(
            task_id="dice-calibration",
            family="dice_chess",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="machine-calibration",
            family="machine_reach",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="dice-skip",
            family="dice_chess",
            difficulty=1,
            evidence=-1,
            phase=DirectorPhase.ROTATION,
            skipped=True,
        ),
    )

    decision = decide_next_task(seed=88, families=families, history=history)

    assert decision.family == "machine_reach"
    assert decision.phase == DirectorPhase.ROTATION
    assert decision.reason == "skipped_task_diversity_rotation"
    assert decision.parent_task_id == "machine-calibration"


def test_skip_can_leave_an_unfinished_locked_chapter() -> None:
    history = (
        CompletedTask(
            task_id="chapter-skip",
            family="geo_zendo",
            difficulty=3,
            evidence=-1,
            phase=DirectorPhase.CHAPTER,
            chapter_stage=2,
            skipped=True,
        ),
    )

    decision = decide_next_task(seed=7, families=FAMILIES, history=history)

    assert decision.family != "geo_zendo"
    assert decision.phase == DirectorPhase.CALIBRATION


def test_failed_chapter_remediation_can_leave_the_chapter_temporarily() -> None:
    history = [
        CompletedTask(
            task_id="dice-calibration",
            family="dice_chess",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="machine-calibration",
            family="machine_reach",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="chapter-remediation",
            family="geo_zendo",
            difficulty=2,
            evidence=-1,
            phase=DirectorPhase.REMEDIATION,
            chapter_stage=2,
        ),
    ]

    decision = decide_next_task(seed=88, families=FAMILIES, history=history)

    assert decision.phase == DirectorPhase.ROTATION
    assert decision.reason == "remediation_cap_weighted_rotation"
    assert decision.family != "geo_zendo"


def test_rotation_uses_weighted_coverage_debt() -> None:
    families = (
        FamilySettings(family="dice_chess", weight=3),
        FamilySettings(family="machine_reach", weight=1),
    )
    history = (
        CompletedTask(
            task_id="dice-calibration",
            family="dice_chess",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="machine-calibration",
            family="machine_reach",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
    )

    decision = decide_next_task(seed=13, families=families, history=history)

    assert decision.phase == DirectorPhase.ROTATION
    assert decision.reason == "weighted_coverage_debt"
    assert decision.family == "dice_chess"
    assert decision.parent_task_id == "dice-calibration"


def test_weighted_rotation_never_repeats_the_latest_family() -> None:
    families = (
        FamilySettings(family="heavy", weight=100),
        FamilySettings(family="light", weight=1),
    )
    history = (
        CompletedTask(
            task_id="light-calibration",
            family="light",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
        CompletedTask(
            task_id="heavy-calibration",
            family="heavy",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
    )

    decision = decide_next_task(seed=13, families=families, history=history)

    # Coverage debt strongly favours ``heavy``, but diversity is a hard
    # invariant while another enabled family exists.
    assert decision.family == "light"


def test_recent_evidence_raises_and_lowers_per_family_level() -> None:
    family = (
        FamilySettings(
            family="dice_chess",
            initial_difficulty=2,
            max_difficulty=3,
        ),
    )
    promotion_history = tuple(
        CompletedTask(
            task_id=f"success-{index}",
            family="dice_chess",
            difficulty=2,
            evidence=evidence,
        )
        for index, evidence in enumerate((1, 1, 0), start=1)
    )
    demotion_history = tuple(
        CompletedTask(
            task_id=f"failure-{index}",
            family="dice_chess",
            difficulty=2,
            evidence=evidence,
            phase=(
                DirectorPhase.REMEDIATION
                if index == 3
                else DirectorPhase.ROTATION
            ),
        )
        for index, evidence in enumerate((-1, -1, 0), start=1)
    )

    promoted = decide_next_task(seed=1, families=family, history=promotion_history)
    demoted = decide_next_task(seed=1, families=family, history=demotion_history)

    assert promoted.difficulty == 3
    assert demoted.difficulty == 1


def test_difficulty_stays_within_one_and_configured_maximum() -> None:
    family = (FamilySettings(family="dice_chess", max_difficulty=3),)
    upper_history = tuple(
        CompletedTask(
            task_id=f"upper-{index}",
            family="dice_chess",
            difficulty=3,
            evidence=1,
        )
        for index in range(3)
    )
    lower_history = tuple(
        CompletedTask(
            task_id=f"lower-{index}",
            family="dice_chess",
            difficulty=1,
            evidence=-1,
            phase=DirectorPhase.REMEDIATION,
        )
        for index in range(3)
    )

    assert (
        decide_next_task(seed=2, families=family, history=upper_history).difficulty
        == 3
    )
    assert (
        decide_next_task(seed=2, families=family, history=lower_history).difficulty
        == 1
    )
