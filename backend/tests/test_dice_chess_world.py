from __future__ import annotations

from fractions import Fraction
from math import gcd

import pytest

from app.environments.chess_world.dice_chess import PIECE_CODES
from app.environments.chess_world.dice_chess_mission import (
    GENERATOR_VERSION as LEGACY_GENERATOR_VERSION,
    generate_dice_chess_mission_task,
)
from app.environments.chess_world.dice_chess_world import (
    GENERATOR_VERSION,
    INVENTORY_KIND,
    REGION_LABELS,
    evaluate_dice_chess_world_answer,
    generate_dice_chess_world_task,
)


def _piece_count(board: list[list[str | None]]) -> int:
    return sum(cell is not None for row in board for cell in row)


def _piece_types_in_region(
    board: list[list[str | None]],
    region: str,
) -> set[str]:
    represented: set[str] = set()
    for row_index, row in enumerate(board):
        rank_index = 7 - row_index
        for file_index, cell in enumerate(row):
            if cell is None:
                continue
            if region == "whole_board":
                included = True
            elif region == "left_half":
                included = file_index <= 3
            elif region == "right_half":
                included = file_index >= 4
            elif region == "upper_half":
                included = rank_index >= 4
            elif region == "lower_half":
                included = rank_index <= 3
            elif region == "light_squares":
                included = (file_index + rank_index) % 2 == 1
            elif region == "dark_squares":
                included = (file_index + rank_index) % 2 == 0
            else:
                raise AssertionError(f"Unexpected region: {region}")
            if included:
                represented.add(cell[1])
    return represented


@pytest.mark.parametrize("difficulty", (1, 2, 3, 5))
def test_world_generator_is_deterministic_board_grounded_and_exact(
    difficulty: int,
) -> None:
    for seed in range(100):
        public, private = generate_dice_chess_world_task(
            seed=seed,
            difficulty=difficulty,
        )
        assert (public, private) == generate_dice_chess_world_task(
            seed=seed,
            difficulty=difficulty,
        )

        assert len(public["board"]) == 8
        assert all(len(row) == 8 for row in public["board"])
        assert all(
            cell is None
            or (
                len(cell) == 2
                and cell[0] in {"w", "b"}
                and cell[1] in PIECE_CODES
            )
            for row in public["board"]
            for cell in row
        )
        assert public["sample_space_size"] == 6
        assert len(public["die"]["faces"]) == 6
        assert set(public["die"]["faces"]) <= set(PIECE_CODES)

        favorable_faces = private["favorable_faces"]
        assert 0 < favorable_faces < 6
        exact = private["probability"]
        probability = Fraction(exact["numerator"], exact["denominator"])
        assert gcd(exact["numerator"], exact["denominator"]) == 1
        assert probability == Fraction(favorable_faces, 6)
        assert 0 < probability < 1

        if difficulty <= 2:
            assert public["kind"] == INVENTORY_KIND
            assert 8 <= _piece_count(public["board"]) <= 16
            assert "не обязана быть легальной шахматной позицией" in public["prompt"]
            region = private["region_key"]
            represented = _piece_types_in_region(public["board"], region)
            assert represented == set(private["represented_piece_types"])
            independently_favorable = sum(
                face in represented
                for face in public["die"]["faces"]
            )
            assert independently_favorable == favorable_faces
            if difficulty == 1:
                assert region == "whole_board"
                assert "На всей доске" in public["event_description"]
            else:
                assert region in REGION_LABELS
                assert REGION_LABELS[region] in public["event_description"]
        else:
            assert public["kind"] == "dice_chess_position_probability"
            assert private["mission_variant"] == "legal_position_probability"


@pytest.mark.parametrize(
    ("answer", "correct", "parsed"),
    [
        ("1/2", True, True),
        ("0,5", True, True),
        ("50%", True, True),
        ("1/3", False, True),
        ("150%", False, False),
        ("не знаю", False, False),
    ],
)
def test_world_evaluator_uses_exact_probability_contract(
    answer: str,
    correct: bool,
    parsed: bool,
) -> None:
    evaluation = evaluate_dice_chess_world_answer(
        answer=answer,
        private_state={
            "probability": {
                "numerator": 1,
                "denominator": 2,
            }
        },
    )

    assert evaluation["correct"] is correct
    assert evaluation["parsed"] is parsed


def test_v2_legacy_generator_remains_callable_and_unchanged() -> None:
    assert GENERATOR_VERSION == "dice-chess-world-v3"
    assert LEGACY_GENERATOR_VERSION == "dice-chess-mission-v2"

    public, private = generate_dice_chess_mission_task(seed=17, difficulty=1)

    assert public["kind"] == "dice_chess_probability"
    assert "board" not in public
    assert private["mission_variant"] == "dice_probability"
