from __future__ import annotations

import itertools
import random
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

FAMILY_KEY = "chess_coverage"
GENERATOR_VERSION = "chess-coverage-v1"
PUBLIC_KIND = "chess_coverage"

PIECE_LABELS = {
    "K": "король",
    "Q": "ферзь",
    "R": "ладья",
    "B": "слон",
    "N": "конь",
}
PIECE_BASE_WEIGHT = {"K": 2, "N": 3, "B": 3, "R": 4, "Q": 6}
_DONE = frozenset({"done", "готово", "готов", "решено"})
_CANDIDATE_ID = re.compile(r"\bC\d+\b", re.IGNORECASE)


@dataclass(frozen=True)
class CoverageTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    completed: bool
    reason: str
    message: str
    normalized_input: str
    evaluation_state: dict[str, Any]


def _inside(row: int, col: int, size: int) -> bool:
    return 0 <= row < size and 0 <= col < size


def attacked_cells(piece: str, row: int, col: int, size: int) -> set[tuple[int, int]]:
    if piece == "K":
        vectors = (
            (-1, -1), (-1, 0), (-1, 1),
            (0, -1), (0, 1),
            (1, -1), (1, 0), (1, 1),
        )
        return {
            (row + dr, col + dc)
            for dr, dc in vectors
            if _inside(row + dr, col + dc, size)
        }
    if piece == "N":
        vectors = (
            (-2, -1), (-2, 1), (-1, -2), (-1, 2),
            (1, -2), (1, 2), (2, -1), (2, 1),
        )
        return {
            (row + dr, col + dc)
            for dr, dc in vectors
            if _inside(row + dr, col + dc, size)
        }

    directions: list[tuple[int, int]] = []
    if piece in {"Q", "R"}:
        directions.extend(((-1, 0), (1, 0), (0, -1), (0, 1)))
    if piece in {"Q", "B"}:
        directions.extend(((-1, -1), (-1, 1), (1, -1), (1, 1)))
    attacked: set[tuple[int, int]] = set()
    for dr, dc in directions:
        next_row, next_col = row + dr, col + dc
        while _inside(next_row, next_col, size):
            attacked.add((next_row, next_col))
            next_row += dr
            next_col += dc
    return attacked


def _coverage_mask(
    candidate: dict[str, Any],
    targets: list[tuple[int, int]],
    size: int,
) -> int:
    attacked = attacked_cells(
        str(candidate["piece"]),
        int(candidate["row"]),
        int(candidate["col"]),
        size,
    )
    return sum(1 << index for index, target in enumerate(targets) if target in attacked)


def _optimal_solutions(
    candidates: list[dict[str, Any]],
    targets: list[tuple[int, int]],
    size: int,
) -> tuple[int, list[tuple[str, ...]]] | None:
    full_mask = (1 << len(targets)) - 1
    masks = [_coverage_mask(candidate, targets, size) for candidate in candidates]
    best_weight: int | None = None
    solutions: list[tuple[str, ...]] = []
    for subset in range(1, 1 << len(candidates)):
        weight = 0
        coverage = 0
        selected: list[str] = []
        for index, candidate in enumerate(candidates):
            if subset >> index & 1:
                weight += int(candidate["weight"])
                if best_weight is not None and weight > best_weight:
                    break
                coverage |= masks[index]
                selected.append(str(candidate["id"]))
        else:
            if coverage != full_mask:
                continue
            if best_weight is None or weight < best_weight:
                best_weight = weight
                solutions = [tuple(selected)]
            elif weight == best_weight:
                solutions.append(tuple(selected))
    if best_weight is None:
        return None
    return best_weight, solutions


def _piece_pool(difficulty: int) -> tuple[str, ...]:
    if difficulty <= 1:
        return ("N", "B", "R")
    if difficulty <= 3:
        return ("N", "B", "R", "K")
    return ("N", "B", "R", "K", "Q")


def _candidate(
    *,
    rng: random.Random,
    index: int,
    size: int,
    difficulty: int,
    occupied: set[tuple[int, int]],
) -> dict[str, Any]:
    available = [
        (row, col)
        for row in range(size)
        for col in range(size)
        if (row, col) not in occupied
    ]
    row, col = rng.choice(available)
    occupied.add((row, col))
    piece = rng.choice(_piece_pool(difficulty))
    weight = PIECE_BASE_WEIGHT[piece] + rng.randint(0, 3)
    return {
        "id": f"C{index}",
        "piece": piece,
        "piece_label": PIECE_LABELS[piece],
        "row": row,
        "col": col,
        "weight": weight,
    }


def generate_chess_coverage_task(
    *, seed: int, difficulty: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = max(1, min(5, int(difficulty)))
    rng = random.Random(f"{GENERATOR_VERSION}:{seed}:{difficulty}")
    size = 5 if difficulty <= 2 else 6 if difficulty <= 4 else 7
    candidate_count = 6 + difficulty
    target_count = 4 + difficulty

    for _ in range(600):
        occupied: set[tuple[int, int]] = set()
        candidates = [
            _candidate(
                rng=rng,
                index=index,
                size=size,
                difficulty=difficulty,
                occupied=occupied,
            )
            for index in range(1, candidate_count + 1)
        ]
        witness_count = 2 if difficulty <= 2 else 3
        witness = rng.sample(candidates, witness_count)
        witness_attacks = [
            attacked_cells(
                str(candidate["piece"]),
                int(candidate["row"]),
                int(candidate["col"]),
                size,
            )
            - occupied
            for candidate in witness
        ]
        mandatory: set[tuple[int, int]] = set()
        valid_witness = True
        for index, attacks in enumerate(witness_attacks):
            other = set().union(
                *(value for other_index, value in enumerate(witness_attacks) if other_index != index)
            )
            unique = sorted(attacks - other)
            if not unique:
                valid_witness = False
                break
            mandatory.add(rng.choice(unique))
        if not valid_witness:
            continue
        union = sorted(set().union(*witness_attacks) - mandatory)
        if len(union) < target_count - len(mandatory):
            continue
        targets = sorted(
            mandatory
            | set(rng.sample(union, target_count - len(mandatory)))
        )
        masks = [_coverage_mask(candidate, targets, size) for candidate in candidates]
        if any(mask == 0 for mask in masks):
            continue
        optimum = _optimal_solutions(candidates, targets, size)
        if optimum is None:
            continue
        optimal_weight, solutions = optimum
        if len(solutions) != 1 or not 2 <= len(solutions[0]) <= 4:
            continue
        break
    else:
        raise RuntimeError("Unable to generate a non-degenerate chess coverage task")

    public = {
        "kind": PUBLIC_KIND,
        "family": FAMILY_KEY,
        "prompt": (
            "Расставьте фигуры на отмеченных позициях так, чтобы каждая "
            "целевая клетка была под боем хотя бы одной выбранной фигуры. "
            "У каждой фигуры указана стоимость. Найдите расстановку с "
            "минимальной суммарной стоимостью. Фигуры не перекрывают линии боя."
        ),
        "board_size": size,
        "targets": [{"row": row, "col": col} for row, col in targets],
        "candidates": deepcopy(candidates),
        "selected_ids": [],
        "covered_targets": [],
        "total_weight": 0,
        "all_covered": False,
        "response_hint": (
            "Нажимайте на фигуры, чтобы добавить или убрать их. "
            "Затем нажмите «Зафиксировать расстановку» или отправьте /answer done."
        ),
    }
    private = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": difficulty,
        "board_size": size,
        "targets": [[row, col] for row, col in targets],
        "candidates": deepcopy(candidates),
        "selected_ids": [],
        "optimal_weight": optimal_weight,
        "optimal_solutions": [list(solution) for solution in solutions],
        "interaction": {
            "placement_count": 0,
            "removal_count": 0,
            "reset_count": 0,
            "first_action_latency_ms": None,
            "processed_actions": {},
        },
    }
    return public, private


def _selection_state(
    selected_ids: list[str], private_state: dict[str, Any]
) -> dict[str, Any]:
    candidates = {
        str(candidate["id"]): candidate
        for candidate in private_state["candidates"]
    }
    targets = [tuple(point) for point in private_state["targets"]]
    size = int(private_state["board_size"])
    covered: set[tuple[int, int]] = set()
    total_weight = 0
    for candidate_id in selected_ids:
        candidate = candidates[candidate_id]
        total_weight += int(candidate["weight"])
        attacked = attacked_cells(
            str(candidate["piece"]),
            int(candidate["row"]),
            int(candidate["col"]),
            size,
        )
        covered.update(target for target in targets if target in attacked)
    return {
        "covered_targets": [
            {"row": row, "col": col} for row, col in sorted(covered)
        ],
        "covered_count": len(covered),
        "target_count": len(targets),
        "total_weight": total_weight,
        "all_covered": len(covered) == len(targets),
    }


def transition_chess_coverage_action(
    *,
    action_type: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    client_action_id: str,
    op_id: str | None = None,
    first_action_latency_ms: int | None = None,
) -> CoverageTransition:
    normalized_type = action_type.strip().casefold()
    if normalized_type not in {"apply_op", "reset"}:
        raise ValueError("Chess coverage action must be apply_op or reset")
    candidate_id = (op_id or "").strip().upper()
    if normalized_type == "apply_op" and not candidate_id:
        raise ValueError("apply_op requires op_id")
    normalized_input = (
        f"apply_op:{candidate_id}" if normalized_type == "apply_op" else "reset"
    )
    action_id = client_action_id.strip()
    if not action_id:
        raise ValueError("client_action_id must not be empty")

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    interaction = next_private["interaction"]
    processed = interaction["processed_actions"]
    previous = processed.get(action_id)
    if previous is not None:
        if previous["normalized_input"] != normalized_input:
            raise ValueError("client_action_id was reused with another action")
        state = _selection_state(next_private["selected_ids"], next_private)
        return CoverageTransition(
            public_state=next_public,
            private_state=next_private,
            accepted=bool(previous["accepted"]),
            completed=False,
            reason=str(previous["reason"]),
            message=str(previous["message"]),
            normalized_input=normalized_input,
            evaluation_state={**state, **_interaction_counts(interaction)},
        )

    if interaction["first_action_latency_ms"] is None and first_action_latency_ms is not None:
        interaction["first_action_latency_ms"] = max(0, int(first_action_latency_ms))

    selected = list(next_private["selected_ids"])
    candidate_ids = {str(candidate["id"]) for candidate in next_private["candidates"]}
    accepted = False
    if normalized_type == "reset":
        if selected:
            selected = []
            interaction["reset_count"] = int(interaction["reset_count"]) + 1
            accepted = True
            reason = "reset"
            message = "Расстановка возвращена в начало."
        else:
            reason = "already_at_start"
            message = "Расстановка уже пустая."
    elif candidate_id not in candidate_ids:
        reason = "unknown_candidate"
        message = "Такой фигуры нет в списке доступных позиций."
    elif candidate_id in selected:
        selected.remove(candidate_id)
        interaction["removal_count"] = int(interaction["removal_count"]) + 1
        accepted = True
        reason = "removed"
        message = f"Фигура {candidate_id} убрана."
    else:
        selected.append(candidate_id)
        selected.sort(key=lambda value: int(value[1:]))
        interaction["placement_count"] = int(interaction["placement_count"]) + 1
        accepted = True
        reason = "placed"
        message = f"Фигура {candidate_id} добавлена."

    next_private["selected_ids"] = selected
    state = _selection_state(selected, next_private)
    next_public.update(
        {
            "selected_ids": list(selected),
            "covered_targets": state["covered_targets"],
            "total_weight": state["total_weight"],
            "all_covered": state["all_covered"],
        }
    )
    message += (
        f" Покрыто {state['covered_count']} из {state['target_count']}; "
        f"стоимость {state['total_weight']}."
    )
    processed[action_id] = {
        "normalized_input": normalized_input,
        "accepted": accepted,
        "reason": reason,
        "message": message,
    }
    return CoverageTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=accepted,
        completed=False,
        reason=reason,
        message=message,
        normalized_input=normalized_input,
        evaluation_state={**state, **_interaction_counts(interaction)},
    )


def _interaction_counts(interaction: dict[str, Any]) -> dict[str, Any]:
    return {
        "placement_count": int(interaction.get("placement_count") or 0),
        "removal_count": int(interaction.get("removal_count") or 0),
        "reset_count": int(interaction.get("reset_count") or 0),
        "first_action_latency_ms": interaction.get("first_action_latency_ms"),
    }


def evaluate_chess_coverage_answer(
    *, answer: str, private_state: dict[str, Any]
) -> dict[str, Any]:
    normalized = answer.strip().casefold()
    submitted_ids = [value.upper() for value in _CANDIDATE_ID.findall(answer)]
    if normalized in _DONE:
        selected = list(private_state.get("selected_ids") or [])
        parsed = True
    elif submitted_ids:
        selected = list(dict.fromkeys(submitted_ids))
        valid = {str(candidate["id"]) for candidate in private_state["candidates"]}
        parsed = all(candidate_id in valid for candidate_id in selected)
    else:
        selected = []
        parsed = False

    state = _selection_state(selected, private_state) if parsed else {
        "covered_count": 0,
        "target_count": len(private_state["targets"]),
        "total_weight": 0,
        "all_covered": False,
    }
    optimal_weight = int(private_state["optimal_weight"])
    correct = bool(
        parsed
        and state["all_covered"]
        and int(state["total_weight"]) == optimal_weight
    )
    return {
        "accepted": True,
        "parsed": parsed,
        "correct": correct,
        "should_finalize": True,
        "continuous_score": 1.0 if correct else 0.0,
        "selected_ids": selected,
        "selected_weight": int(state["total_weight"]),
        "optimal_weight": optimal_weight,
        "covered_count": int(state["covered_count"]),
        "target_count": int(state["target_count"]),
        "all_covered": bool(state["all_covered"]),
        **_interaction_counts(private_state.get("interaction") or {}),
    }
