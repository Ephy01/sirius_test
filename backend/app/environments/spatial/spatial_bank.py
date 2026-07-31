"""spatial_bank: AIG-style single-select rotation and assembly items.

Two templates, four options each:

* rotation-match — the reference is a polyomino of six to nine cells with
  no non-trivial symmetry (a mandatory filter: otherwise a mirrored
  distractor would coincide with the correct rotation); options are one
  proper rotation, two reflections and one near-shape;
* assembly — a target figure and four pairs of parts, exactly one pair
  tiles the target (checked by brute force over placements and
  isometries; sizes are small).

Every generated item is verified by full isometry enumeration to have
exactly one correct option.
"""

from __future__ import annotations

import random
import re
from functools import lru_cache
from typing import Any

FAMILY_KEY = "spatial_bank"
GENERATOR_VERSION = "spatial-bank-v1"
PUBLIC_KIND = "spatial_bank"

ROTATION_VARIANT = "rotation_match"
ASSEMBLY_VARIANT = "assembly"
OPTION_IDS = ("V1", "V2", "V3", "V4")

Cell = tuple[int, int]
Shape = frozenset[Cell]


def _normalize(cells: Any) -> Shape:
    cells = list(cells)
    min_row = min(row for row, _column in cells)
    min_column = min(column for _row, column in cells)
    return frozenset(
        (row - min_row, column - min_column)
        for row, column in cells
    )


def _rotate(shape: Shape) -> Shape:
    return _normalize((column, -row) for row, column in shape)


def _reflect(shape: Shape) -> Shape:
    return _normalize((row, -column) for row, column in shape)


@lru_cache(maxsize=1 << 15)
def _isometries(shape: Shape) -> tuple[Shape, ...]:
    """All eight images of ``shape`` under rotations and reflections."""

    images = []
    current = _normalize(shape)
    for _ in range(4):
        images.append(current)
        current = _rotate(current)
    mirrored = _reflect(_normalize(shape))
    for _ in range(4):
        images.append(mirrored)
        mirrored = _rotate(mirrored)
    return tuple(images)


def _rotations(shape: Shape) -> tuple[Shape, ...]:
    return _isometries(shape)[:4]


def _has_nontrivial_symmetry(shape: Shape) -> bool:
    images = _isometries(shape)
    return len(set(images)) < 8


def _is_rotation_of(candidate: Shape, reference: Shape) -> bool:
    return _normalize(candidate) in _rotations(reference)


def _is_isometric(candidate: Shape, reference: Shape) -> bool:
    return _normalize(candidate) in _isometries(reference)


def _connected(shape: Shape) -> bool:
    if not shape:
        return False
    cells = set(shape)
    start = next(iter(cells))
    stack = [start]
    seen = {start}
    while stack:
        row, column = stack.pop()
        for neighbor in (
            (row - 1, column),
            (row + 1, column),
            (row, column - 1),
            (row, column + 1),
        ):
            if neighbor in cells and neighbor not in seen:
                seen.add(neighbor)
                stack.append(neighbor)
    return len(seen) == len(cells)


def _grow_polyomino(rng: random.Random, size: int) -> Shape:
    cells = {(0, 0)}
    while len(cells) < size:
        frontier = sorted(
            {
                neighbor
                for row, column in cells
                for neighbor in (
                    (row - 1, column),
                    (row + 1, column),
                    (row, column - 1),
                    (row, column + 1),
                )
                if neighbor not in cells
            }
        )
        cells.add(rng.choice(frontier))
    return _normalize(cells)


def _near_shape(rng: random.Random, shape: Shape) -> Shape | None:
    """Move one cell to keep the silhouette close but non-isometric."""

    if len(shape) < 4:
        # Every connected 2–3-cell shape is isometric to its one-cell
        # mutations far too often; do not waste attempts on them.
        return None
    cells = set(shape)
    for _ in range(24):
        removable = [
            cell
            for cell in sorted(cells)
            if _connected(frozenset(cells - {cell}))
        ]
        if not removable:
            return None
        removed = rng.choice(removable)
        remaining = cells - {removed}
        frontier = sorted(
            {
                neighbor
                for row, column in remaining
                for neighbor in (
                    (row - 1, column),
                    (row + 1, column),
                    (row, column - 1),
                    (row, column + 1),
                )
                if neighbor not in remaining and neighbor != removed
            }
        )
        if not frontier:
            continue
        added = rng.choice(frontier)
        candidate = _normalize(remaining | {added})
        if len(candidate) != len(shape):
            continue
        if _connected(candidate) and not _is_isometric(candidate, shape):
            return candidate
    return None


def _serialize(shape: Shape) -> list[list[int]]:
    return [
        [row, column]
        for row, column in sorted(_normalize(shape))
    ]


def _can_assemble(target: Shape, first: Shape, second: Shape) -> bool:
    """Brute force: do the two parts tile the target exactly?"""

    target_cells = set(_normalize(target))
    if len(first) + len(second) != len(target_cells):
        return False
    target_rows = max(row for row, _column in target_cells) + 1
    target_columns = max(column for _row, column in target_cells) + 1
    for first_image in set(_isometries(first)):
        for row_offset in range(target_rows):
            for column_offset in range(target_columns):
                placed_first = {
                    (row + row_offset, column + column_offset)
                    for row, column in first_image
                }
                if not placed_first <= target_cells:
                    continue
                remainder = frozenset(target_cells - placed_first)
                if _is_isometric(remainder, second):
                    return True
    return False


def _split_target(
    rng: random.Random,
    target: Shape,
) -> tuple[Shape, Shape] | None:
    cells = sorted(target)
    for _ in range(64):
        # Both parts stay at four cells or more, so near-shape mutations
        # of either part can escape its isometry class.
        first_size = rng.randint(4, len(cells) - 4)
        seed_cell = rng.choice(cells)
        part = {seed_cell}
        while len(part) < first_size:
            frontier = sorted(
                {
                    neighbor
                    for row, column in part
                    for neighbor in (
                        (row - 1, column),
                        (row + 1, column),
                        (row, column - 1),
                        (row, column + 1),
                    )
                    if neighbor in target and neighbor not in part
                }
            )
            if not frontier:
                break
            part.add(rng.choice(frontier))
        if len(part) != first_size:
            continue
        remainder = frozenset(set(target) - part)
        if _connected(remainder):
            return _normalize(part), _normalize(remainder)
    return None


def _rotation_item(
    rng: random.Random,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    size = min(9, 5 + difficulty)
    reference: Shape | None = None
    for _ in range(128):
        candidate = _grow_polyomino(rng, size)
        # Mandatory filter: with any non-trivial symmetry a reflected
        # distractor would coincide with a rotation of the reference.
        if not _has_nontrivial_symmetry(candidate):
            reference = candidate
            break
    if reference is None:
        return None
    rotation_steps = rng.choice((1, 2, 3))
    correct = reference
    for _ in range(rotation_steps):
        correct = _rotate(correct)
    mirrored = _reflect(reference)
    first_reflection = mirrored
    for _ in range(rng.randrange(4)):
        first_reflection = _rotate(first_reflection)
    second_reflection = mirrored
    for _ in range(rng.randrange(4)):
        second_reflection = _rotate(second_reflection)
    if second_reflection == first_reflection:
        second_reflection = _rotate(first_reflection)
    near = _near_shape(rng, reference)
    if near is None:
        return None
    options = [correct, first_reflection, second_reflection, near]
    order = list(range(4))
    rng.shuffle(order)
    shuffled = [options[index] for index in order]
    correct_option = OPTION_IDS[order.index(0)]

    matches = [
        option_id
        for option_id, shape in zip(OPTION_IDS, shuffled, strict=True)
        if _is_rotation_of(shape, reference)
    ]
    if matches != [correct_option]:
        return None

    public = {
        "variant": ROTATION_VARIANT,
        "prompt": (
            "Слева показан эталон. Ровно один из четырёх вариантов — "
            "тот же эталон, повёрнутый на 90°, 180° или 270° "
            "(без отражений). Выберите его."
        ),
        "reference": _serialize(reference),
        "options": [
            {"id": option_id, "cells": _serialize(shape)}
            for option_id, shape in zip(OPTION_IDS, shuffled, strict=True)
        ],
    }
    private = {
        "variant": ROTATION_VARIANT,
        "correct_option": correct_option,
        "rotation_steps": rotation_steps,
    }
    return public, private


def _assembly_item(
    rng: random.Random,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    size = 8 + (1 if difficulty >= 3 else 0) + (1 if difficulty >= 5 else 0)
    target = _grow_polyomino(rng, size)
    split = _split_target(rng, target)
    if split is None:
        return None
    correct_pair = split
    distractors: list[tuple[Shape, Shape]] = []
    for _ in range(96):
        if len(distractors) == 3:
            break
        # Mutating the larger part keeps the distractor plausible and
        # avoids tiny parts whose mutations stay isometric.
        mutate_first = len(correct_pair[0]) >= len(correct_pair[1])
        mutated = _near_shape(
            rng,
            correct_pair[0] if mutate_first else correct_pair[1],
        )
        if mutated is None:
            return None
        candidate = (
            (mutated, correct_pair[1])
            if mutate_first
            else (correct_pair[0], mutated)
        )
        if _can_assemble(target, candidate[0], candidate[1]):
            continue
        if any(
            _is_isometric(candidate[0], existing[0])
            and _is_isometric(candidate[1], existing[1])
            for existing in distractors
        ):
            continue
        distractors.append(candidate)
    if len(distractors) != 3:
        return None

    options = [correct_pair, *distractors]
    order = list(range(4))
    rng.shuffle(order)
    shuffled = [options[index] for index in order]
    correct_option = OPTION_IDS[order.index(0)]

    assemblable = [
        option_id
        for option_id, (first, second) in zip(
            OPTION_IDS,
            shuffled,
            strict=True,
        )
        if _can_assemble(target, first, second)
    ]
    if assemblable != [correct_option]:
        return None

    public = {
        "variant": ASSEMBLY_VARIANT,
        "prompt": (
            "Показана целевая фигура и четыре пары частей. Ровно одна "
            "пара складывается в цель без наложений и пропусков "
            "(части можно поворачивать и отражать). Выберите её."
        ),
        "target": _serialize(target),
        "options": [
            {
                "id": option_id,
                "parts": [_serialize(first), _serialize(second)],
            }
            for option_id, (first, second) in zip(
                OPTION_IDS,
                shuffled,
                strict=True,
            )
        ],
    }
    private = {
        "variant": ASSEMBLY_VARIANT,
        "correct_option": correct_option,
    }
    return public, private


def generate_spatial_bank_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("spatial_bank difficulty must be from 1 to 5")
    rng = random.Random(seed)
    variant = rng.choice((ROTATION_VARIANT, ASSEMBLY_VARIANT))
    for _ in range(256):
        item = (
            _rotation_item(rng, difficulty)
            if variant == ROTATION_VARIANT
            else _assembly_item(rng, difficulty)
        )
        if item is None:
            continue
        item_public, item_private = item
        public = {
            "kind": PUBLIC_KIND,
            "family": FAMILY_KEY,
            **item_public,
            "response_hint": "Выберите вариант: /answer V2.",
        }
        private = {
            "family": FAMILY_KEY,
            "generator_version": GENERATOR_VERSION,
            "difficulty": difficulty,
            **item_private,
        }
        return public, private
    raise RuntimeError(
        f"Unable to generate spatial_bank at difficulty {difficulty}"
    )


def _parse_option(answer: str) -> str | None:
    normalized = re.sub(
        r"^\s*/?answer\b",
        "",
        answer.strip().casefold(),
    ).strip()
    match = re.fullmatch(r"v?([1-4])", normalized)
    return f"V{match.group(1)}" if match else None


def evaluate_spatial_bank_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    submitted = _parse_option(answer)
    parsed = submitted is not None
    correct = parsed and submitted == private_state["correct_option"]
    return {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": int(private_state["difficulty"]),
        "variant": str(private_state["variant"]),
        "correct": bool(correct),
        "parsed": parsed,
        "submitted_option": submitted,
        "continuous_score": 1.0 if correct else 0.0,
        "evidence": 1 if correct else -1,
    }


__all__ = [
    "ASSEMBLY_VARIANT",
    "FAMILY_KEY",
    "GENERATOR_VERSION",
    "PUBLIC_KIND",
    "ROTATION_VARIANT",
    "evaluate_spatial_bank_answer",
    "generate_spatial_bank_task",
]
