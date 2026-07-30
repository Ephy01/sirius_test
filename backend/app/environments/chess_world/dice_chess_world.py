from __future__ import annotations

import random
from fractions import Fraction
from typing import Any

from .dice_chess import PIECE_CODES, evaluate_dice_chess_answer
from .dice_chess_position import generate_dice_chess_position_task

FAMILY_KEY = "dice_chess"
GENERATOR_VERSION = "dice-chess-world-v3"
POSITION_TASK_MIN_DIFFICULTY = 3
INVENTORY_KIND = "dice_chess_board_inventory_probability"

DIE_FACE_COUNT = 6
MIN_BOARD_PIECES = 8
MAX_BOARD_PIECES = 16

REGION_LABELS = {
    "left_half": "левой половине доски (вертикали a–d)",
    "right_half": "правой половине доски (вертикали e–h)",
    "upper_half": "верхней половине доски (горизонтали 5–8)",
    "lower_half": "нижней половине доски (горизонтали 1–4)",
    "light_squares": "светлых клетках",
    "dark_squares": "тёмных клетках",
}


def _is_in_region(region: str, file_index: int, rank_index: int) -> bool:
    if region == "left_half":
        return file_index <= 3
    if region == "right_half":
        return file_index >= 4
    if region == "upper_half":
        return rank_index >= 4
    if region == "lower_half":
        return rank_index <= 3
    # a1 is dark; files and ranks are zero-indexed here.
    if region == "light_squares":
        return (file_index + rank_index) % 2 == 1
    if region == "dark_squares":
        return (file_index + rank_index) % 2 == 0
    raise ValueError(f"Unsupported inventory region: {region!r}")


def _serialize_placements(
    placements: list[tuple[int, int, str]],
) -> list[list[str | None]]:
    board: list[list[str | None]] = [[None for _ in range(8)] for _ in range(8)]
    for square, color_index, piece_code in placements:
        file_index = square % 8
        rank_index = square // 8
        row_index = 7 - rank_index
        color_prefix = "w" if color_index == 0 else "b"
        board[row_index][file_index] = f"{color_prefix}{piece_code}"
    return board


def _whole_board_placements(
    rng: random.Random,
    piece_count: int,
) -> tuple[list[tuple[int, int, str]], tuple[str, ...]]:
    represented_count = rng.randint(2, len(PIECE_CODES) - 1)
    represented = tuple(sorted(rng.sample(PIECE_CODES, represented_count)))
    piece_types = list(represented)
    piece_types.extend(
        rng.choice(represented)
        for _ in range(piece_count - len(piece_types))
    )
    rng.shuffle(piece_types)
    squares = rng.sample(range(64), piece_count)
    placements = [
        (square, rng.randrange(2), piece_code)
        for square, piece_code in zip(squares, piece_types, strict=True)
    ]
    return placements, represented


def _regional_placements(
    rng: random.Random,
    piece_count: int,
    region: str,
) -> tuple[list[tuple[int, int, str]], tuple[str, ...]]:
    inside_squares = [
        square
        for square in range(64)
        if _is_in_region(region, square % 8, square // 8)
    ]
    outside_squares = [
        square
        for square in range(64)
        if square not in inside_squares
    ]
    inside_count = rng.randint(3, min(8, piece_count - 2))
    represented_count = rng.randint(1, min(len(PIECE_CODES) - 1, inside_count))
    represented = tuple(sorted(rng.sample(PIECE_CODES, represented_count)))

    inside_types = list(represented)
    inside_types.extend(
        rng.choice(represented)
        for _ in range(inside_count - len(inside_types))
    )
    outside_types = [
        rng.choice(PIECE_CODES)
        for _ in range(piece_count - inside_count)
    ]
    rng.shuffle(inside_types)
    placements = [
        (square, rng.randrange(2), piece_code)
        for square, piece_code in zip(
            rng.sample(inside_squares, inside_count),
            inside_types,
            strict=True,
        )
    ]
    placements.extend(
        (square, rng.randrange(2), piece_code)
        for square, piece_code in zip(
            rng.sample(outside_squares, piece_count - inside_count),
            outside_types,
            strict=True,
        )
    )
    rng.shuffle(placements)
    return placements, represented


def _build_die(
    rng: random.Random,
    represented: tuple[str, ...],
) -> tuple[tuple[str, ...], int]:
    absent = tuple(code for code in PIECE_CODES if code not in represented)
    favorable_face_count = rng.randint(1, DIE_FACE_COUNT - 1)
    faces = [
        rng.choice(represented)
        for _ in range(favorable_face_count)
    ]
    faces.extend(
        rng.choice(absent)
        for _ in range(DIE_FACE_COUNT - favorable_face_count)
    )
    rng.shuffle(faces)
    return tuple(faces), favorable_face_count


def generate_dice_chess_inventory_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate a board-grounded probability task for levels one and two."""

    if difficulty not in (1, 2):
        raise ValueError("inventory tasks support only difficulty 1 or 2")

    rng = random.Random(seed)
    piece_count = rng.randint(MIN_BOARD_PIECES, MAX_BOARD_PIECES)
    if difficulty == 1:
        region_key = "whole_board"
        region_label = "всей доске"
        placements, represented = _whole_board_placements(rng, piece_count)
        event_type = "type_present_on_board"
    else:
        region_key = rng.choice(sorted(REGION_LABELS))
        region_label = REGION_LABELS[region_key]
        placements, represented = _regional_placements(
            rng,
            piece_count,
            region_key,
        )
        event_type = "type_present_in_region"

    faces, favorable_face_count = _build_die(rng, represented)
    probability = Fraction(favorable_face_count, DIE_FACE_COUNT)
    board = _serialize_placements(placements)
    event_description = (
        "На всей доске имеется хотя бы одна фигура выпавшего типа."
        if difficulty == 1
        else (
            "Имеется хотя бы одна фигура выпавшего типа на "
            f"{region_label}."
        )
    )

    public_state: dict[str, Any] = {
        "kind": INVENTORY_KIND,
        "prompt": (
            "Перед вами условная расстановка фигур на доске 8×8. "
            "Она не обязана быть легальной шахматной позицией: "
            "учитываются только типы фигур и область, указанная в событии. "
            "Бросают один шестигранный кубик, все его грани равновероятны. "
            "Найдите вероятность описанного события."
        ),
        "board": board,
        "die": {
            "id": "piece-die",
            "label": "Кубик фигур",
            "faces": list(faces),
        },
        "event_description": event_description,
        "sample_space_size": DIE_FACE_COUNT,
        "response_hint": (
            "Введите вероятность сокращённой дробью a/b, "
            "десятичным числом или в процентах."
        ),
    }
    private_state: dict[str, Any] = {
        "event_type": event_type,
        "region_key": region_key,
        "represented_piece_types": list(represented),
        "absent_piece_types": [
            code for code in PIECE_CODES if code not in represented
        ],
        "favorable_faces": favorable_face_count,
        "total_faces": DIE_FACE_COUNT,
        "probability": {
            "numerator": probability.numerator,
            "denominator": probability.denominator,
        },
        "difficulty": difficulty,
        "mission_variant": "board_inventory_probability",
    }
    return public_state, private_state


def generate_dice_chess_world_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate the v3 Dice & Chess trajectory with a board at every level."""

    if difficulty < 1:
        raise ValueError("difficulty must be at least 1")
    if difficulty < POSITION_TASK_MIN_DIFFICULTY:
        return generate_dice_chess_inventory_task(
            seed=seed,
            difficulty=difficulty,
        )

    public_state, private_state = generate_dice_chess_position_task(
        seed=seed,
        difficulty=difficulty,
    )
    return public_state, {
        **private_state,
        "mission_variant": "legal_position_probability",
    }


def evaluate_dice_chess_world_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    return evaluate_dice_chess_answer(
        answer=answer,
        private_state=private_state,
    )
