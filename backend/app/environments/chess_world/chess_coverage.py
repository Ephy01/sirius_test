from __future__ import annotations

import random
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

FAMILY_KEY = "chess_coverage"
LEGACY_GENERATOR_VERSION = "chess-coverage-v1"
GENERATOR_VERSION = "chess-coverage-v2"
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


def generate_legacy_chess_coverage_task(
    *, seed: int, difficulty: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = max(1, min(5, int(difficulty)))
    rng = random.Random(f"{LEGACY_GENERATOR_VERSION}:{seed}:{difficulty}")
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
        "generator_version": LEGACY_GENERATOR_VERSION,
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


def transition_legacy_chess_coverage_action(
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


def evaluate_legacy_chess_coverage_answer(
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


CUSTOM_PIECES: tuple[dict[str, Any], ...] = (
    {
        "id": "N",
        "label": "конь",
        "base_cost": 2,
        "repeat_surcharge": 1,
        "limit": 3,
        "move_label": "Г-прыжок: 1×2",
        "offsets": (
            (-2, -1), (-2, 1), (-1, -2), (-1, 2),
            (1, -2), (1, 2), (2, -1), (2, 1),
        ),
    },
    {
        "id": "B",
        "label": "слон",
        "base_cost": 3,
        "repeat_surcharge": 2,
        "limit": 3,
        "move_label": "диагональные прыжки 2×2 и 1×3",
        "offsets": (
            (-3, -1), (-3, 1), (-2, -2), (-1, -3), (-1, 3),
            (1, -3), (1, 3), (2, -2), (2, 2), (3, -1), (3, 1),
        ),
    },
    {
        "id": "R",
        "label": "ладья",
        "base_cost": 4,
        "repeat_surcharge": 2,
        "limit": 2,
        "move_label": "прямой прыжок на 2 или 3 клетки",
        "offsets": (
            (-3, 0), (-2, 0), (0, -3), (0, -2),
            (0, 2), (0, 3), (2, 0), (3, 0),
        ),
    },
    {
        "id": "Q",
        "label": "ферзь",
        "base_cost": 6,
        "repeat_surcharge": 5,
        "limit": 2,
        "move_label": "корона: Г-прыжок и диагональ 2×2",
        "offsets": (
            (-2, -2), (-2, -1), (-2, 1), (-2, 2),
            (-1, -2), (-1, 2), (1, -2), (1, 2),
            (2, -2), (2, -1), (2, 1), (2, 2),
        ),
    },
)

_PLACE_ACTION = re.compile(r"^place:([NBRQ]):([0-7]):([0-7])$", re.IGNORECASE)
_REMOVE_ACTION = re.compile(r"^remove:(P\d+)$", re.IGNORECASE)


def _piece_map(piece_types: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(piece["id"]): piece for piece in piece_types}


def _custom_attacks(
    piece: dict[str, Any], row: int, col: int, size: int = 8
) -> set[tuple[int, int]]:
    return {
        (row + int(dr), col + int(dc))
        for dr, dc in piece["offsets"]
        if _inside(row + int(dr), col + int(dc), size)
    }


def _marginal_cost(piece: dict[str, Any], existing_count: int) -> int:
    return int(piece["base_cost"]) + int(piece["repeat_surcharge"]) * existing_count


def _placement_cost(
    placements: list[dict[str, Any]], piece_types: list[dict[str, Any]]
) -> int:
    definitions = _piece_map(piece_types)
    counts = {piece_id: 0 for piece_id in definitions}
    total = 0
    for placement in placements:
        piece_id = str(placement["piece"])
        total += _marginal_cost(definitions[piece_id], counts[piece_id])
        counts[piece_id] += 1
    return total


def _placement_state(
    placements: list[dict[str, Any]], private_state: dict[str, Any]
) -> dict[str, Any]:
    definitions = _piece_map(private_state["piece_types"])
    targets = [tuple(point) for point in private_state["targets"]]
    covered: set[tuple[int, int]] = set()
    counts = {piece_id: 0 for piece_id in definitions}
    public_placements: list[dict[str, Any]] = []
    total_cost = 0
    for placement in sorted(
        placements,
        key=lambda item: int(str(item["id"])[1:]),
    ):
        piece_id = str(placement["piece"])
        definition = definitions[piece_id]
        cost = _marginal_cost(definition, counts[piece_id])
        counts[piece_id] += 1
        total_cost += cost
        row, col = int(placement["row"]), int(placement["col"])
        attacked = _custom_attacks(definition, row, col)
        covered.update(target for target in targets if target in attacked)
        public_placements.append(
            {
                "id": str(placement["id"]),
                "piece": piece_id,
                "row": row,
                "col": col,
                "cost": cost,
            }
        )
    return {
        "placements": public_placements,
        "piece_counts": counts,
        "covered_targets": [
            {"row": row, "col": col} for row, col in sorted(covered)
        ],
        "covered_count": len(covered),
        "target_count": len(targets),
        "total_cost": total_cost,
        "all_covered": len(covered) == len(targets),
    }


def _solve_placement_problem(
    *,
    targets: list[tuple[int, int]],
    piece_types: list[dict[str, Any]],
    max_placements: int,
    incumbent: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]], int]:
    full_mask = (1 << len(targets)) - 1
    target_set = set(targets)
    piece_index = {
        str(piece["id"]): index for index, piece in enumerate(piece_types)
    }
    options: list[dict[str, Any]] = []
    for row in range(8):
        for col in range(8):
            if (row, col) in target_set:
                continue
            for piece in piece_types:
                mask = sum(
                    1 << index
                    for index, target in enumerate(targets)
                    if target in _custom_attacks(piece, row, col)
                )
                if mask:
                    options.append(
                        {
                            "piece": str(piece["id"]),
                            "row": row,
                            "col": col,
                            "square": row * 8 + col,
                            "mask": mask,
                        }
                    )
    by_target = [
        [option for option in options if int(option["mask"]) & (1 << index)]
        for index in range(len(targets))
    ]
    best_cost = _placement_cost(incumbent, piece_types)
    best_solution = deepcopy(incumbent)
    memo: dict[tuple[int, tuple[int, ...], int], int] = {}
    visited_nodes = 0

    def search(
        mask: int,
        counts: tuple[int, ...],
        occupied: int,
        cost: int,
        selected: list[dict[str, Any]],
    ) -> None:
        nonlocal best_cost, best_solution, visited_nodes
        visited_nodes += 1
        if mask == full_mask:
            if cost < best_cost:
                best_cost = cost
                best_solution = deepcopy(selected)
            return
        if len(selected) >= max_placements or cost >= best_cost:
            return
        key = (mask, counts, occupied)
        previous_cost = memo.get(key)
        if previous_cost is not None and previous_cost <= cost:
            return
        memo[key] = cost

        chosen_options: list[dict[str, Any]] | None = None
        for target_index in range(len(targets)):
            if mask & (1 << target_index):
                continue
            legal = []
            for option in by_target[target_index]:
                square_bit = 1 << int(option["square"])
                index = piece_index[str(option["piece"])]
                if occupied & square_bit:
                    continue
                if counts[index] >= int(piece_types[index]["limit"]):
                    continue
                legal.append(option)
            if not legal:
                return
            if chosen_options is None or len(legal) < len(chosen_options):
                chosen_options = legal

        assert chosen_options is not None
        ranked: list[tuple[float, int, int, dict[str, Any]]] = []
        for option in chosen_options:
            index = piece_index[str(option["piece"])]
            added = int(option["mask"]) & ~mask
            gain = added.bit_count()
            incremental = _marginal_cost(piece_types[index], counts[index])
            ranked.append((incremental / gain, incremental, -gain, option))
        ranked.sort(key=lambda item: (item[0], item[1], item[2]))
        if cost + min(item[1] for item in ranked) >= best_cost:
            return

        for _ratio, incremental, _negative_gain, option in ranked:
            if cost + incremental >= best_cost:
                continue
            index = piece_index[str(option["piece"])]
            next_counts = list(counts)
            next_counts[index] += 1
            placement = {
                "id": f"P{len(selected) + 1}",
                "piece": str(option["piece"]),
                "row": int(option["row"]),
                "col": int(option["col"]),
            }
            search(
                mask | int(option["mask"]),
                tuple(next_counts),
                occupied | (1 << int(option["square"])),
                cost + incremental,
                [*selected, placement],
            )

    search(0, tuple(0 for _ in piece_types), 0, 0, [])
    return best_cost, best_solution, visited_nodes


def _public_piece_types(piece_types: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(piece["id"]),
            "label": str(piece["label"]),
            "base_cost": int(piece["base_cost"]),
            "repeat_surcharge": int(piece["repeat_surcharge"]),
            "limit": int(piece["limit"]),
            "move_label": str(piece["move_label"]),
            "offsets": [
                {"row": int(row), "col": int(col)}
                for row, col in piece["offsets"]
            ],
        }
        for piece in piece_types
    ]


def generate_chess_coverage_task(
    *, seed: int, difficulty: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = max(1, min(5, int(difficulty)))
    rng = random.Random(f"{GENERATOR_VERSION}:{seed}:{difficulty}")
    piece_types = [deepcopy(piece) for piece in CUSTOM_PIECES]
    max_placements = 4 if difficulty <= 2 else 5 if difficulty <= 4 else 6
    witness_count = 3 if difficulty <= 2 else 4 if difficulty <= 4 else 5
    target_count = 5 + difficulty

    for _ in range(180):
        squares = rng.sample(range(64), witness_count)
        witness: list[dict[str, Any]] = []
        type_counts = {str(piece["id"]): 0 for piece in piece_types}
        for index, square in enumerate(squares, start=1):
            available = [
                piece
                for piece in piece_types
                if type_counts[str(piece["id"])] < int(piece["limit"])
            ]
            piece = rng.choices(available, weights=[5, 4, 3, 2][:len(available)])[0]
            piece_id = str(piece["id"])
            type_counts[piece_id] += 1
            witness.append(
                {
                    "id": f"P{index}",
                    "piece": piece_id,
                    "row": square // 8,
                    "col": square % 8,
                }
            )
        occupied = {(int(item["row"]), int(item["col"])) for item in witness}
        witness_attacks = [
            _custom_attacks(
                _piece_map(piece_types)[str(item["piece"])],
                int(item["row"]),
                int(item["col"]),
            ) - occupied
            for item in witness
        ]
        mandatory: set[tuple[int, int]] = set()
        for index, attacks in enumerate(witness_attacks):
            other_attacks = set().union(
                *(
                    value
                    for other_index, value in enumerate(witness_attacks)
                    if other_index != index
                )
            )
            unique = sorted(attacks - other_attacks)
            if unique:
                mandatory.add(rng.choice(unique))
        union = sorted(set().union(*witness_attacks) - mandatory)
        if len(mandatory) < 2 or len(union) < target_count - len(mandatory):
            continue
        targets = sorted(
            mandatory | set(rng.sample(union, target_count - len(mandatory)))
        )
        optimal_cost, solution, solver_nodes = _solve_placement_problem(
            targets=targets,
            piece_types=piece_types,
            max_placements=max_placements,
            incumbent=witness,
        )
        if not 2 <= len(solution) <= max_placements:
            continue
        if len({str(item["piece"]) for item in solution}) < 2:
            continue
        break
    else:
        raise RuntimeError("Unable to generate a custom chess placement task")

    public_piece_types = _public_piece_types(piece_types)
    public = {
        "kind": PUBLIC_KIND,
        "family": FAMILY_KEY,
        "variant": "custom_jump_placement",
        "prompt": (
            "На доске 8×8 отмечены целевые клетки. Выберите фигуру в панели "
            "и расставьте фигуры так, чтобы каждая цель находилась под боем. "
            "Фигуры ходят не по обычным шахматным правилам: их прыжки показаны "
            "в панели, промежуточные клетки не имеют значения. Стоимость каждой "
            "следующей фигуры одного типа возрастает. Покройте все цели с "
            f"минимальной стоимостью, используя не более {max_placements} фигур."
        ),
        "board_size": 8,
        "targets": [{"row": row, "col": col} for row, col in targets],
        "piece_types": public_piece_types,
        "placements": [],
        "covered_targets": [],
        "piece_counts": {str(piece["id"]): 0 for piece in piece_types},
        "total_cost": 0,
        "all_covered": False,
        "max_placements": max_placements,
        "response_hint": (
            "Сначала выберите тип фигуры, затем нажмите на свободную клетку. "
            "Нажатие на установленную фигуру убирает её."
        ),
    }
    private = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "variant": "custom_jump_placement",
        "difficulty": difficulty,
        "board_size": 8,
        "targets": [[row, col] for row, col in targets],
        "piece_types": deepcopy(piece_types),
        "placements": [],
        "max_placements": max_placements,
        "next_placement_number": 1,
        "optimal_cost": optimal_cost,
        "optimal_placements": deepcopy(solution),
        "solver_nodes": solver_nodes,
        "interaction": {
            "placement_count": 0,
            "removal_count": 0,
            "reset_count": 0,
            "first_action_latency_ms": None,
            "processed_actions": {},
        },
    }
    return public, private


def transition_chess_coverage_action(
    *,
    action_type: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    client_action_id: str,
    op_id: str | None = None,
    first_action_latency_ms: int | None = None,
) -> CoverageTransition:
    if private_state.get("variant") != "custom_jump_placement":
        return transition_legacy_chess_coverage_action(
            action_type=action_type,
            public_state=public_state,
            private_state=private_state,
            client_action_id=client_action_id,
            op_id=op_id,
            first_action_latency_ms=first_action_latency_ms,
        )
    normalized_type = action_type.strip().casefold()
    if normalized_type not in {"apply_op", "reset"}:
        raise ValueError("Chess placement action must be apply_op or reset")
    normalized_op = (op_id or "").strip()
    if normalized_type == "apply_op" and not normalized_op:
        raise ValueError("apply_op requires op_id")
    normalized_input = (
        normalized_op.casefold() if normalized_type == "apply_op" else "reset"
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
        state = _placement_state(next_private["placements"], next_private)
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

    placements = list(next_private["placements"])
    definitions = _piece_map(next_private["piece_types"])
    targets = {tuple(point) for point in next_private["targets"]}
    accepted = False
    if normalized_type == "reset":
        if placements:
            placements = []
            interaction["reset_count"] = int(interaction["reset_count"]) + 1
            accepted, reason = True, "reset"
            message = "Расстановка возвращена в начало."
        else:
            reason, message = "already_at_start", "На доске пока нет фигур."
    else:
        place_match = _PLACE_ACTION.fullmatch(normalized_op)
        remove_match = _REMOVE_ACTION.fullmatch(normalized_op)
        if remove_match:
            placement_id = remove_match.group(1).upper()
            before = len(placements)
            placements = [item for item in placements if item["id"] != placement_id]
            if len(placements) < before:
                interaction["removal_count"] = int(interaction["removal_count"]) + 1
                accepted, reason = True, "removed"
                message = f"Фигура {placement_id} убрана."
            else:
                reason, message = "unknown_placement", "Такой фигуры на доске нет."
        elif place_match:
            piece_id = place_match.group(1).upper()
            row, col = int(place_match.group(2)), int(place_match.group(3))
            counts = {
                key: sum(1 for item in placements if item["piece"] == key)
                for key in definitions
            }
            if piece_id not in definitions:
                reason, message = "unknown_piece", "Такого типа фигуры нет."
            elif (row, col) in targets:
                reason, message = "target_cell", "На целевую клетку ставить фигуру нельзя."
            elif any(int(item["row"]) == row and int(item["col"]) == col for item in placements):
                reason, message = "occupied_cell", "Клетка уже занята другой фигурой."
            elif len(placements) >= int(next_private["max_placements"]):
                reason, message = "piece_budget", "Лимит фигур исчерпан."
            elif counts[piece_id] >= int(definitions[piece_id]["limit"]):
                reason, message = "piece_limit", "Лимит фигур этого типа исчерпан."
            else:
                placement_id = f"P{int(next_private['next_placement_number'])}"
                next_private["next_placement_number"] = (
                    int(next_private["next_placement_number"]) + 1
                )
                placements.append(
                    {
                        "id": placement_id,
                        "piece": piece_id,
                        "row": row,
                        "col": col,
                    }
                )
                interaction["placement_count"] = int(interaction["placement_count"]) + 1
                accepted, reason = True, "placed"
                message = f"Фигура {placement_id} установлена."
        else:
            reason = "invalid_action"
            message = "Не удалось распознать действие с фигурой."

    next_private["placements"] = placements
    state = _placement_state(placements, next_private)
    next_public.update(
        {
            "placements": state["placements"],
            "piece_counts": state["piece_counts"],
            "covered_targets": state["covered_targets"],
            "total_cost": state["total_cost"],
            "all_covered": state["all_covered"],
        }
    )
    message += (
        f" Покрыто {state['covered_count']} из {state['target_count']}; "
        f"стоимость {state['total_cost']}."
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


def evaluate_chess_coverage_answer(
    *, answer: str, private_state: dict[str, Any]
) -> dict[str, Any]:
    if private_state.get("variant") != "custom_jump_placement":
        return evaluate_legacy_chess_coverage_answer(
            answer=answer,
            private_state=private_state,
        )
    parsed = answer.strip().casefold() in _DONE
    state = _placement_state(private_state.get("placements") or [], private_state)
    optimal_cost = int(private_state["optimal_cost"])
    correct = bool(parsed and state["all_covered"] and state["total_cost"] == optimal_cost)
    return {
        "accepted": True,
        "parsed": parsed,
        "correct": correct,
        "should_finalize": True,
        "continuous_score": 1.0 if correct else 0.0,
        "placements": state["placements"],
        "selected_cost": int(state["total_cost"]),
        "optimal_cost": optimal_cost,
        "cost_regret": max(0, int(state["total_cost"]) - optimal_cost),
        "covered_count": int(state["covered_count"]),
        "target_count": int(state["target_count"]),
        "all_covered": bool(state["all_covered"]),
        **_interaction_counts(private_state.get("interaction") or {}),
    }
