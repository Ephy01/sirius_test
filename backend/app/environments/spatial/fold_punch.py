"""fold_punch («дырокол»): mentally unfold a punched paper sheet.

An 8×8 sheet is folded in half two or three times (horizontally or
vertically; difficulties four and five add one final diagonal fold of a
square sheet), then one or two holes are punched through every layer.
The participant sees the fold sequence and the punched folded sheet and
must mark every hole cell of the unfolded sheet.

Two independent models keep the checker honest:

* the generator runs a forward layer-stack simulation (each folded cell
  knows the original cells beneath it);
* :func:`unfold_holes` replays the folds backwards, reflecting the hole
  set at each unfold (transposition for the diagonal fold).

Tests cross-check both models cell by cell on small sheets.
"""

from __future__ import annotations

import random
import re
from typing import Any

FAMILY_KEY = "fold_punch"
GENERATOR_VERSION = "fold-punch-v1"
PUBLIC_KIND = "fold_punch"

SHEET_SIZE = 8

# (axis, direction) pairs; directions name the half that moves.
VERTICAL_RIGHT_ONTO_LEFT = ("vertical", "right_onto_left")
VERTICAL_LEFT_ONTO_RIGHT = ("vertical", "left_onto_right")
HORIZONTAL_TOP_ONTO_BOTTOM = ("horizontal", "top_onto_bottom")
HORIZONTAL_BOTTOM_ONTO_TOP = ("horizontal", "bottom_onto_top")
DIAGONAL_MAIN = ("diagonal", "upper_right_onto_lower_left")

FOLD_LABELS = {
    VERTICAL_RIGHT_ONTO_LEFT: "правую половину налево",
    VERTICAL_LEFT_ONTO_RIGHT: "левую половину направо",
    HORIZONTAL_TOP_ONTO_BOTTOM: "верхнюю половину вниз",
    HORIZONTAL_BOTTOM_ONTO_TOP: "нижнюю половину вверх",
    DIAGONAL_MAIN: "по диагонали: правый верхний угол к левому нижнему",
}

Cell = tuple[int, int]  # (row, column), zero-based, row 0 is the top row.


def _forward_fold_stacks(
    folds: list[tuple[str, str]],
) -> tuple[dict[Cell, list[Cell]], int, int, bool]:
    """Forward simulation: folded cell → stack of original cells."""

    width = SHEET_SIZE
    height = SHEET_SIZE
    stacks: dict[Cell, list[Cell]] = {
        (row, column): [(row, column)]
        for row in range(height)
        for column in range(width)
    }
    triangle = False
    for axis, direction in folds:
        next_stacks: dict[Cell, list[Cell]] = {}
        if axis == "vertical":
            half = width // 2
            for row in range(height):
                for column in range(half):
                    if direction == "right_onto_left":
                        base = stacks[(row, column)]
                        moved = stacks[(row, width - 1 - column)]
                        next_stacks[(row, column)] = [*moved, *base]
                    else:
                        base = stacks[(row, column + half)]
                        moved = stacks[(row, half - 1 - column)]
                        next_stacks[(row, column)] = [*moved, *base]
            width = half
        elif axis == "horizontal":
            half = height // 2
            for row in range(half):
                for column in range(width):
                    if direction == "top_onto_bottom":
                        base = stacks[(row + half, column)]
                        moved = stacks[(half - 1 - row, column)]
                        next_stacks[(row, column)] = [*moved, *base]
                    else:
                        base = stacks[(row, column)]
                        moved = stacks[(height - 1 - row, column)]
                        next_stacks[(row, column)] = [*moved, *base]
            height = half
        else:
            if width != height:
                raise ValueError("diagonal fold requires a square sheet")
            # The upper-right triangle (column > row) folds onto the
            # lower-left one across the main diagonal.
            for row in range(height):
                for column in range(row + 1):
                    base = stacks[(row, column)]
                    if column == row:
                        next_stacks[(row, column)] = list(base)
                    else:
                        moved = stacks[(column, row)]
                        next_stacks[(row, column)] = [*moved, *base]
            triangle = True
        stacks = next_stacks
    return stacks, width, height, triangle


def unfold_holes(
    folds: list[tuple[str, str]],
    holes: set[Cell],
) -> set[Cell]:
    """Checker: replay folds backwards, mirroring the hole set."""

    width = SHEET_SIZE
    height = SHEET_SIZE
    sizes: list[tuple[int, int]] = []
    for axis, _direction in folds:
        sizes.append((width, height))
        if axis == "vertical":
            width //= 2
        elif axis == "horizontal":
            height //= 2
    unfolded = set(holes)
    for (axis, direction), (full_width, full_height) in zip(
        reversed(folds),
        reversed(sizes),
        strict=True,
    ):
        if axis == "diagonal":
            unfolded |= {(column, row) for row, column in unfolded}
            continue
        mirrored: set[Cell] = set()
        for row, column in unfolded:
            if axis == "vertical":
                if direction == "right_onto_left":
                    mirrored.add((row, full_width - 1 - column))
                else:
                    mirrored.add((row, column + full_width // 2))
                    mirrored.add((row, full_width // 2 - 1 - column))
            else:
                if direction == "top_onto_bottom":
                    mirrored.add((row + full_height // 2, column))
                    mirrored.add((full_height // 2 - 1 - row, column))
                else:
                    mirrored.add((full_height - 1 - row, column))
        if axis == "vertical" and direction == "right_onto_left":
            unfolded |= mirrored
        elif axis == "horizontal" and direction == "bottom_onto_top":
            unfolded |= mirrored
        else:
            unfolded = mirrored
    return unfolded


def generate_fold_punch_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("fold_punch difficulty must be from 1 to 5")
    rng = random.Random(seed)
    fold_count = 2 if difficulty <= 2 else 3
    hole_count = 1 if difficulty == 1 else 2
    use_diagonal = difficulty >= 4

    for _ in range(256):
        folds: list[tuple[str, str]] = []
        width = SHEET_SIZE
        height = SHEET_SIZE
        planar_folds = fold_count - (1 if use_diagonal else 0)
        for _ in range(planar_folds):
            options: list[tuple[str, str]] = []
            if width >= 2:
                options.extend(
                    (VERTICAL_RIGHT_ONTO_LEFT, VERTICAL_LEFT_ONTO_RIGHT)
                )
            if height >= 2:
                options.extend(
                    (HORIZONTAL_TOP_ONTO_BOTTOM, HORIZONTAL_BOTTOM_ONTO_TOP)
                )
            fold = rng.choice(options)
            folds.append(fold)
            if fold[0] == "vertical":
                width //= 2
            else:
                height //= 2
        if use_diagonal:
            if width != height:
                continue
            folds.append(DIAGONAL_MAIN)

        stacks, folded_width, folded_height, triangle = _forward_fold_stacks(
            folds
        )
        available = sorted(stacks)
        if len(available) < hole_count:
            continue
        holes = sorted(rng.sample(available, hole_count))
        expected: set[Cell] = set()
        for hole in holes:
            expected.update(stacks[hole])
        checker = unfold_holes(folds, set(holes))
        if checker != expected:
            raise RuntimeError(
                "fold_punch checker diverged from the forward simulation"
            )
        if len(expected) < 2:
            continue

        public = {
            "kind": PUBLIC_KIND,
            "family": FAMILY_KEY,
            "variant": "unfold_holes",
            "prompt": (
                "Лист 8×8 сложили в показанном порядке и пробили дырки в "
                "сложенном состоянии. Отметьте все клетки развёрнутого "
                "листа, в которых окажутся дырки."
            ),
            "sheet_size": SHEET_SIZE,
            "folds": [
                {
                    "axis": axis,
                    "direction": direction,
                    "label": f"Сложить {FOLD_LABELS[(axis, direction)]}",
                }
                for axis, direction in folds
            ],
            "folded": {
                "width": folded_width,
                "height": folded_height,
                "triangle": triangle,
                "holes": [[row, column] for row, column in holes],
            },
            "response_hint": (
                "Кликните клетки на сетке или перечислите их: "
                "/answer 2,3 5,8 (строка,столбец от левого верхнего угла)."
            ),
        }
        private = {
            "family": FAMILY_KEY,
            "generator_version": GENERATOR_VERSION,
            "difficulty": difficulty,
            "folds": [[axis, direction] for axis, direction in folds],
            "punched_holes": [[row, column] for row, column in holes],
            "expected_holes": sorted(
                [row, column] for row, column in expected
            ),
        }
        return public, private
    raise RuntimeError(
        f"Unable to generate fold_punch at difficulty {difficulty}"
    )


def _parse_cells(answer: str) -> set[Cell] | None:
    normalized = re.sub(r"^\s*/?answer\b", "", answer.strip(), flags=re.I)
    tokens = [
        token
        for token in re.split(r"[;\s]+", normalized.strip())
        if token
    ]
    if not tokens:
        return None
    cells: set[Cell] = set()
    for token in tokens:
        match = re.fullmatch(r"(\d)[,.:](\d)", token)
        if match is None:
            return None
        row = int(match.group(1)) - 1
        column = int(match.group(2)) - 1
        if not (0 <= row < SHEET_SIZE and 0 <= column < SHEET_SIZE):
            return None
        cells.add((row, column))
    return cells


def evaluate_fold_punch_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    expected = {
        (int(row), int(column))
        for row, column in private_state["expected_holes"]
    }
    submitted = _parse_cells(answer)
    parsed = submitted is not None
    intersection = len(expected & submitted) if submitted else 0
    union = len(expected | submitted) if submitted else len(expected)
    jaccard = intersection / union if union else 0.0
    exact = parsed and submitted == expected
    return {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": int(private_state["difficulty"]),
        "correct": bool(exact),
        "parsed": parsed,
        "submitted_cells": (
            sorted([row + 1, column + 1] for row, column in submitted)
            if submitted
            else None
        ),
        "expected_count": len(expected),
        "jaccard": jaccard,
        "continuous_score": jaccard if parsed else 0.0,
        "evidence": 1 if exact else -1,
    }


__all__ = [
    "FAMILY_KEY",
    "GENERATOR_VERSION",
    "PUBLIC_KIND",
    "SHEET_SIZE",
    "evaluate_fold_punch_answer",
    "generate_fold_punch_task",
    "unfold_holes",
]
