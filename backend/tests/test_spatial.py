"""Acceptance battery for fold_punch (stage S)."""

from __future__ import annotations

from app.environments.spatial.fold_punch import (
    SHEET_SIZE,
    evaluate_fold_punch_answer,
    generate_fold_punch_task,
    unfold_holes,
)

FORBIDDEN_PUBLIC_KEYS = {
    "expected_holes",
    "punched_holes",
    "correct_option",
    "private_state",
    "seed",
}


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested_value in value.values()
            for nested_key in _nested_keys(nested_value)
        }
    if isinstance(value, list):
        return {
            nested_key
            for item in value
            for nested_key in _nested_keys(item)
        }
    return set()


def _forward_brute_force(
    folds: list[tuple[str, str]],
    holes: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Independent forward check: fold coordinates cell by cell."""

    def fold_cell(cell, width, height, axis, direction):
        row, column = cell
        if axis == "vertical":
            half = width // 2
            if direction == "right_onto_left":
                return (row, column if column < half else width - 1 - column)
            return (
                row,
                (column - half) if column >= half else half - 1 - column,
            )
        if axis == "horizontal":
            half = height // 2
            if direction == "top_onto_bottom":
                return (
                    (row - half) if row >= half else half - 1 - row,
                    column,
                )
            return (row if row < half else height - 1 - row, column)
        return (max(row, column), min(row, column))

    expected: set[tuple[int, int]] = set()
    for original_row in range(SHEET_SIZE):
        for original_column in range(SHEET_SIZE):
            cell = (original_row, original_column)
            width = height = SHEET_SIZE
            for axis, direction in folds:
                cell = fold_cell(cell, width, height, axis, direction)
                if axis == "vertical":
                    width //= 2
                elif axis == "horizontal":
                    height //= 2
            if cell in holes:
                expected.add((original_row, original_column))
    return expected


def test_fold_punch_checker_matches_cellwise_brute_force():
    for seed in range(120):
        difficulty = 1 + seed % 5
        _public, private = generate_fold_punch_task(
            seed=seed,
            difficulty=difficulty,
        )
        folds = [(axis, direction) for axis, direction in private["folds"]]
        holes = {
            (int(row), int(column))
            for row, column in private["punched_holes"]
        }
        expected = {
            (int(row), int(column))
            for row, column in private["expected_holes"]
        }
        assert unfold_holes(folds, holes) == expected
        assert _forward_brute_force(folds, holes) == expected


def test_fold_punch_is_deterministic_and_does_not_leak():
    for seed in range(60):
        for difficulty in (1, 3, 4, 5):
            public, private = generate_fold_punch_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert (public, private) == generate_fold_punch_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
            fold_axes = [fold["axis"] for fold in public["folds"]]
            if difficulty >= 4:
                assert fold_axes[-1] == "diagonal"
            else:
                assert "diagonal" not in fold_axes


def test_fold_punch_scores_exact_set_with_jaccard():
    _public, private = generate_fold_punch_task(seed=5, difficulty=3)
    expected = [
        f"{row + 1},{column + 1}"
        for row, column in private["expected_holes"]
    ]
    exact = evaluate_fold_punch_answer(
        answer="/answer " + " ".join(expected),
        private_state=private,
    )
    assert exact["correct"] is True
    assert exact["continuous_score"] == 1.0
    assert exact["evidence"] == 1

    partial = evaluate_fold_punch_answer(
        answer=" ".join(expected[:-1]),
        private_state=private,
    )
    assert partial["correct"] is False
    assert 0.0 < partial["continuous_score"] < 1.0
    assert partial["jaccard"] == partial["continuous_score"]

    malformed = evaluate_fold_punch_answer(
        answer="везде",
        private_state=private,
    )
    assert malformed["parsed"] is False
    assert malformed["continuous_score"] == 0.0


def test_spatial_warm_generation_perf():
    import time

    generate_fold_punch_task(seed=0, difficulty=1)
    started = time.perf_counter()
    for index in range(100):
        generate_fold_punch_task(seed=index, difficulty=1 + index % 5)
    assert time.perf_counter() - started < 5
