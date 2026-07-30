from __future__ import annotations

from typing import Any

from .dice_chess import (
    evaluate_dice_chess_answer,
    generate_dice_chess_task,
)
from .dice_chess_position import generate_dice_chess_position_task

FAMILY_KEY = "dice_chess"
GENERATOR_VERSION = "dice-chess-mission-v2"
POSITION_TASK_MIN_DIFFICULTY = 3


def generate_dice_chess_mission_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate the learning progression used by the Dice & Chess family.

    The first two difficulty levels teach the probability model on dice alone.
    Starting at level three, the same probability contract is grounded in a
    legal chess position. Keeping both variants behind one version makes the
    progression explicit and reproducible for every attempt seed.
    """

    if difficulty < POSITION_TASK_MIN_DIFFICULTY:
        public_state, private_state = generate_dice_chess_task(
            seed=seed,
            difficulty=difficulty,
        )
        variant = "dice_probability"
    else:
        public_state, private_state = generate_dice_chess_position_task(
            seed=seed,
            difficulty=difficulty,
        )
        variant = "position_probability"

    return public_state, {
        **private_state,
        "mission_variant": variant,
    }


def evaluate_dice_chess_mission_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    # Both mission variants intentionally share one answer contract.
    return evaluate_dice_chess_answer(
        answer=answer,
        private_state=private_state,
    )
