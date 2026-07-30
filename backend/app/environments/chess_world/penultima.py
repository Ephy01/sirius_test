from __future__ import annotations

import hashlib
import random
import re
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

FAMILY_KEY = "penultima"
GENERATOR_VERSION = "micro-penultima-v1"
RULE_CATALOG_VERSION = "micro-penultima-rules-v1"

FILES = "abcdefgh"
RANKS = "12345678"
BOARD_SIZE = 8
MAX_GENERATION_ATTEMPTS = 192
RECENT_OBSERVATION_LIMIT = 8

PIECE_NAMES = (
    "Комета",
    "Орбита",
    "Пульсар",
    "Спутник",
    "Фотон",
    "Квазар",
)


@dataclass(frozen=True)
class RuleSpec:
    key: str
    minimum_difficulty: int
    movement: str
    vectors: tuple[tuple[int, int], ...]
    max_distance: int = 1


@dataclass(frozen=True)
class PenultimaTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    completed: bool
    reason: str
    message: str
    normalized_move: str
    evaluation_state: dict[str, Any] | None


ORTHOGONAL_DIRECTIONS = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL_DIRECTIONS = ((1, 1), (1, -1), (-1, 1), (-1, -1))
KING_DIRECTIONS = ORTHOGONAL_DIRECTIONS + DIAGONAL_DIRECTIONS
KNIGHT_VECTORS = (
    (1, 2),
    (2, 1),
    (-1, 2),
    (-2, 1),
    (1, -2),
    (2, -1),
    (-1, -2),
    (-2, -1),
)
CAMEL_VECTORS = (
    (1, 3),
    (3, 1),
    (-1, 3),
    (-3, 1),
    (1, -3),
    (3, -1),
    (-1, -3),
    (-3, -1),
)
ORTHOGONAL_TWO_VECTORS = ((2, 0), (-2, 0), (0, 2), (0, -2))

RULE_CATALOG: tuple[RuleSpec, ...] = (
    RuleSpec("orthogonal-step", 1, "leap", ORTHOGONAL_DIRECTIONS),
    RuleSpec("diagonal-step", 1, "leap", DIAGONAL_DIRECTIONS),
    RuleSpec("king-step", 1, "leap", KING_DIRECTIONS),
    RuleSpec("knight-leap", 2, "leap", KNIGHT_VECTORS),
    RuleSpec("orthogonal-two-leap", 2, "leap", ORTHOGONAL_TWO_VECTORS),
    RuleSpec("camel-leap", 3, "leap", CAMEL_VECTORS),
    RuleSpec("rook-slider-2", 3, "slider", ORTHOGONAL_DIRECTIONS, 2),
    RuleSpec("bishop-slider-2", 3, "slider", DIAGONAL_DIRECTIONS, 2),
    RuleSpec("queen-slider-2", 4, "slider", KING_DIRECTIONS, 2),
    RuleSpec("rook-slider-3", 5, "slider", ORTHOGONAL_DIRECTIONS, 3),
    RuleSpec("bishop-slider-3", 5, "slider", DIAGONAL_DIRECTIONS, 3),
    RuleSpec("queen-slider-3", 6, "slider", KING_DIRECTIONS, 3),
)
RULES_BY_KEY = {rule.key: rule for rule in RULE_CATALOG}

MOVE_PATTERN = re.compile(
    r"^\s*([a-hA-H][1-8])(?:\s*(?:-|:|→|>)\s*|\s+)?([a-hA-H][1-8])\s*$"
)


def coordinate_to_point(coordinate: str) -> tuple[int, int]:
    normalized = coordinate.strip().casefold()
    if len(normalized) != 2 or normalized[0] not in FILES or normalized[1] not in RANKS:
        raise ValueError(f"Invalid board coordinate: {coordinate!r}")
    return FILES.index(normalized[0]), RANKS.index(normalized[1])


def point_to_coordinate(point: tuple[int, int]) -> str:
    file_index, rank_index = point
    if not _inside_board(file_index, rank_index):
        raise ValueError(f"Point is outside the board: {point!r}")
    return f"{FILES[file_index]}{RANKS[rank_index]}"


def parse_move(move: str) -> tuple[str, str, str] | None:
    match = MOVE_PATTERN.fullmatch(move)
    if match is None:
        return None
    source = match.group(1).casefold()
    target = match.group(2).casefold()
    return source, target, f"{source}{target}"


def _inside_board(file_index: int, rank_index: int) -> bool:
    return 0 <= file_index < BOARD_SIZE and 0 <= rank_index < BOARD_SIZE


def _rule_for_key(rule_key: str) -> RuleSpec:
    try:
        return RULES_BY_KEY[rule_key]
    except KeyError as error:
        raise ValueError(f"Unknown Penultima rule: {rule_key!r}") from error


def legal_destinations(
    *,
    square: str,
    rule_key: str,
    blockers: Iterable[str],
) -> tuple[str, ...]:
    rule = _rule_for_key(rule_key)
    origin_file, origin_rank = coordinate_to_point(square)
    blocked = {coordinate.casefold() for coordinate in blockers}
    destinations: set[str] = set()

    if rule.movement == "leap":
        for file_delta, rank_delta in rule.vectors:
            target_file = origin_file + file_delta
            target_rank = origin_rank + rank_delta
            if not _inside_board(target_file, target_rank):
                continue
            target = point_to_coordinate((target_file, target_rank))
            if target not in blocked:
                destinations.add(target)
    elif rule.movement == "slider":
        for file_delta, rank_delta in rule.vectors:
            for distance in range(1, rule.max_distance + 1):
                target_file = origin_file + file_delta * distance
                target_rank = origin_rank + rank_delta * distance
                if not _inside_board(target_file, target_rank):
                    break
                target = point_to_coordinate((target_file, target_rank))
                if target in blocked:
                    break
                destinations.add(target)
    else:
        raise ValueError(f"Unknown Penultima movement type: {rule.movement!r}")
    return tuple(sorted(destinations))


def shortest_path(
    *,
    start: str,
    goal: str,
    rule_key: str,
    blockers: Iterable[str],
) -> list[str] | None:
    normalized_start = start.casefold()
    normalized_goal = goal.casefold()
    if normalized_start == normalized_goal:
        return [normalized_start]

    queue: deque[str] = deque([normalized_start])
    parents: dict[str, str | None] = {normalized_start: None}
    while queue:
        current = queue.popleft()
        for destination in legal_destinations(
            square=current,
            rule_key=rule_key,
            blockers=blockers,
        ):
            if destination in parents:
                continue
            parents[destination] = current
            if destination == normalized_goal:
                path = [normalized_goal]
                cursor = normalized_goal
                while parents[cursor] is not None:
                    cursor = parents[cursor] or normalized_start
                    path.append(cursor)
                return list(reversed(path))
            queue.append(destination)
    return None


def _reachable_distances(
    *,
    start: str,
    rule_key: str,
    blockers: Iterable[str],
) -> dict[str, int]:
    distances = {start: 0}
    queue: deque[str] = deque([start])
    while queue:
        current = queue.popleft()
        for destination in legal_destinations(
            square=current,
            rule_key=rule_key,
            blockers=blockers,
        ):
            if destination in distances:
                continue
            distances[destination] = distances[current] + 1
            queue.append(destination)
    return distances


def _all_squares() -> tuple[str, ...]:
    return tuple(f"{file_name}{rank}" for rank in RANKS for file_name in FILES)


def _desired_distance_range(
    *,
    difficulty: int,
    branch: str,
    previous_distance: int | None,
) -> tuple[int, int]:
    if branch == "remediate":
        return 1, 2
    if branch == "consolidate":
        upper = max(2, min(4, previous_distance or 4))
        return 2, upper
    if branch == "advance" and previous_distance is not None:
        return min(14, previous_distance + 1), min(14, previous_distance + 3)

    minimum = min(5, 2 + max(0, difficulty - 1) // 2)
    return minimum, min(8, minimum + 2)


def _select_goal(
    *,
    rng: random.Random,
    current_square: str,
    rule_key: str,
    blockers: tuple[str, ...],
    desired_range: tuple[int, int],
    required_future_advances: int = 0,
) -> tuple[str, list[str]] | None:
    distances = _reachable_distances(
        start=current_square,
        rule_key=rule_key,
        blockers=blockers,
    )
    minimum, maximum = desired_range
    candidates = [
        square
        for square, distance in distances.items()
        if minimum <= distance <= maximum
    ]
    if required_future_advances > 0:
        candidates = [
            square
            for square in candidates
            if _supports_farther_goals(
                start=square,
                previous_distance=distances[square],
                remaining_advances=required_future_advances,
                rule_key=rule_key,
                blockers=blockers,
            )
        ]
    candidates = sorted(candidates)
    if not candidates:
        if required_future_advances > 0:
            return None
        nonzero = [
            (square, distance)
            for square, distance in distances.items()
            if distance > 0
        ]
        if not nonzero:
            return None
        best_distance = max(distance for _square, distance in nonzero)
        candidates = sorted(
            square for square, distance in nonzero if distance == best_distance
        )

    goal_square = rng.choice(candidates)
    path = shortest_path(
        start=current_square,
        goal=goal_square,
        rule_key=rule_key,
        blockers=blockers,
    )
    if path is None:
        return None
    return goal_square, path


def _supports_farther_goals(
    *,
    start: str,
    previous_distance: int,
    remaining_advances: int,
    rule_key: str,
    blockers: tuple[str, ...],
) -> bool:
    if remaining_advances <= 0:
        return True
    distances = _reachable_distances(
        start=start,
        rule_key=rule_key,
        blockers=blockers,
    )
    candidates = [
        (square, distance)
        for square, distance in distances.items()
        if previous_distance + 1 <= distance <= min(14, previous_distance + 3)
    ]
    if remaining_advances == 1:
        return bool(candidates)
    return any(
        _supports_farther_goals(
            start=square,
            previous_distance=distance,
            remaining_advances=remaining_advances - 1,
            rule_key=rule_key,
            blockers=blockers,
        )
        for square, distance in candidates
    )


def _public_board(
    *,
    current_square: str,
    goal_square: str,
    blockers: Iterable[str],
) -> list[list[str | None]]:
    blocker_set = set(blockers)
    rows: list[list[str | None]] = []
    for rank in range(8, 0, -1):
        row: list[str | None] = []
        for file_name in FILES:
            square = f"{file_name}{rank}"
            if square == current_square:
                row.append("wN")
            elif square == goal_square:
                row.append("bK")
            elif square in blocker_set:
                row.append("bP")
            else:
                row.append(None)
        rows.append(row)
    return rows


def _state_hash_payload(value: object) -> str:
    serialized = repr(value).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()[:16]


def _new_chapter_inputs(
    *,
    rng: random.Random,
    difficulty: int,
    desired_range: tuple[int, int],
    exclude_rule_key: str | None,
) -> tuple[RuleSpec, tuple[str, ...], str, str, list[str]]:
    available_rules = [
        rule for rule in RULE_CATALOG if rule.minimum_difficulty <= difficulty
    ]
    if not available_rules:
        available_rules = [RULE_CATALOG[0]]
    alternatives = [
        rule for rule in available_rules if rule.key != exclude_rule_key
    ]
    if alternatives:
        available_rules = alternatives

    squares = list(_all_squares())
    for _ in range(MAX_GENERATION_ATTEMPTS):
        rule = rng.choice(available_rules)
        blocker_count = min(14, 5 + difficulty // 2 + rng.randrange(4))
        blockers = tuple(sorted(rng.sample(squares, blocker_count)))
        free_squares = [square for square in squares if square not in blockers]
        current_square = rng.choice(free_squares)
        initial_destinations = legal_destinations(
            square=current_square,
            rule_key=rule.key,
            blockers=blockers,
        )
        invalid_free_targets = (
            len(free_squares) - 1 - len(initial_destinations)
        )
        if len(initial_destinations) < 2 or invalid_free_targets < 6:
            continue
        selected_goal = _select_goal(
            rng=rng,
            current_square=current_square,
            rule_key=rule.key,
            blockers=blockers,
            desired_range=desired_range,
            required_future_advances=2,
        )
        if selected_goal is None:
            continue
        goal_square, path = selected_goal
        if not desired_range[0] <= len(path) - 1 <= desired_range[1]:
            continue
        return rule, blockers, current_square, goal_square, path

    # A deterministic open-board fallback. Every catalog graph is symmetric,
    # and the retry loop above normally succeeds long before this branch.
    rule = RULE_CATALOG[0]
    blockers = ("d4", "e5")
    current_square = "b2"
    selected_goal = _select_goal(
        rng=rng,
        current_square=current_square,
        rule_key=rule.key,
        blockers=blockers,
        desired_range=desired_range,
        required_future_advances=2,
    )
    if selected_goal is None:
        raise RuntimeError("Penultima fallback must remain reachable")
    goal_square, path = selected_goal
    return rule, blockers, current_square, goal_square, path


def generate_penultima_task(
    *,
    seed: int,
    difficulty: int,
    context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rng = random.Random(seed)
    generation_context = deepcopy(context) if isinstance(context, dict) else {}
    branch = str(generation_context.get("branch") or "initial")
    parent_task_id = generation_context.get("parent_task_id")
    context_hash = str(
        generation_context.get("context_hash")
        or _state_hash_payload({"branch": branch, "parent_task_id": parent_task_id})
    )
    previous_distance_value = generation_context.get("previous_shortest_path_length")
    previous_distance = (
        previous_distance_value
        if isinstance(previous_distance_value, int)
        and not isinstance(previous_distance_value, bool)
        else None
    )
    desired_range = _desired_distance_range(
        difficulty=difficulty,
        branch=branch,
        previous_distance=previous_distance,
    )

    preserved = generation_context.get("chapter")
    same_chapter = branch in {"advance", "consolidate", "remediate"} and isinstance(
        preserved, dict
    )
    if same_chapter:
        rule = _rule_for_key(str(preserved["rule_key"]))
        blockers = tuple(sorted(str(item) for item in preserved["blockers"]))
        current_square = str(preserved["current_square"])
        selected_goal = _select_goal(
            rng=rng,
            current_square=current_square,
            rule_key=rule.key,
            blockers=blockers,
            desired_range=desired_range,
            required_future_advances=(
                1
                if branch == "advance" and int(preserved["chapter_stage"]) < 3
                else 0
            ),
        )
        if selected_goal is None:
            raise ValueError("Preserved Penultima chapter has no reachable next goal")
        goal_square, path = selected_goal
        chapter_id = str(preserved["chapter_id"])
        chapter_stage = int(preserved["chapter_stage"])
        piece_name = str(preserved["piece_name"])
    else:
        rule, blockers, current_square, goal_square, path = _new_chapter_inputs(
            rng=rng,
            difficulty=difficulty,
            desired_range=desired_range,
            exclude_rule_key=(
                str(generation_context["exclude_rule_key"])
                if generation_context.get("exclude_rule_key") is not None
                else None
            ),
        )
        chapter_id = hashlib.sha256(
            f"{GENERATOR_VERSION}:{seed}:chapter".encode("ascii")
        ).hexdigest()[:16]
        chapter_stage = 1
        piece_name = rng.choice(PIECE_NAMES)

    inherited_observations = generation_context.get("recent_observations")
    recent_observations = (
        deepcopy(inherited_observations[-RECENT_OBSERVATION_LIMIT:])
        if isinstance(inherited_observations, list) and same_chapter
        else []
    )
    shortest_moves = [
        f"{source}{target}" for source, target in zip(path, path[1:])
    ]
    stage_title = {
        1: "Разведка",
        2: "Перенос",
        3: "Маршрут",
    }.get(chapter_stage, "Маршрут")
    public_state: dict[str, Any] = {
        "kind": "penultima_induction",
        "prompt": (
            f"{stage_title}. Доставьте фигуру «{piece_name}» на клетку "
            f"{goal_square}. "
            "Правило её движения скрыто и остаётся неизменным в пределах главы. "
            "Обычные шахматные правила здесь не действуют. "
            "Предлагайте ходы и наблюдайте, какие из них принимает система."
        ),
        "board": _public_board(
            current_square=current_square,
            goal_square=goal_square,
            blockers=blockers,
        ),
        "piece_name": piece_name,
        "current_square": current_square,
        "goal_square": goal_square,
        "chapter_stage": chapter_stage,
        "stage_title": stage_title,
        "accepted_moves": 0,
        "rejected_moves": 0,
        "recent_observations": recent_observations,
        "response_hint": "Введите ход командой /move a1 b2.",
    }
    private_state: dict[str, Any] = {
        "rule_catalog_version": RULE_CATALOG_VERSION,
        "rule_key": rule.key,
        "blockers": list(blockers),
        "current_square": current_square,
        "goal_square": goal_square,
        "initial_square": current_square,
        "shortest_solution": shortest_moves,
        "initial_shortest_path_length": len(shortest_moves),
        "remaining_shortest_solution": shortest_moves,
        "chapter_id": chapter_id,
        "chapter_stage": chapter_stage,
        "piece_name": piece_name,
        "accepted_moves": 0,
        "rejected_moves": 0,
        "recent_observations": recent_observations,
        "difficulty": difficulty,
        "generation": {
            "parent_task_id": parent_task_id,
            "branch": branch,
            "context_hash": context_hash,
            "desired_shortest_path_range": list(desired_range),
        },
    }
    return public_state, private_state


def transition_penultima_move(
    *,
    move: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> PenultimaTransition:
    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    parsed = parse_move(move)
    accepted = False
    completed = False
    evaluation_state: dict[str, Any] | None = None

    if parsed is None:
        source = ""
        target = ""
        normalized_move = move.strip().casefold()
        reason = "invalid_format"
    else:
        source, target, normalized_move = parsed
        current_square = str(next_private["current_square"])
        blockers = tuple(str(item) for item in next_private["blockers"])
        rule_key = str(next_private["rule_key"])
        if source != current_square:
            reason = "wrong_origin"
        elif source == target:
            reason = "same_square"
        elif target in blockers:
            reason = "blocked_destination"
        elif target not in legal_destinations(
            square=current_square,
            rule_key=rule_key,
            blockers=blockers,
        ):
            reason = "rule_rejected"
        else:
            accepted = True
            reason = "accepted"
            next_private["current_square"] = target
            next_private["accepted_moves"] = int(next_private["accepted_moves"]) + 1
            next_public["current_square"] = target
            next_public["accepted_moves"] = int(next_public["accepted_moves"]) + 1
            path = shortest_path(
                start=target,
                goal=str(next_private["goal_square"]),
                rule_key=rule_key,
                blockers=blockers,
            )
            if path is None:
                raise RuntimeError(
                    "A symmetric Penultima rule moved outside the goal component"
                )
            next_private["remaining_shortest_solution"] = [
                f"{path_source}{path_target}"
                for path_source, path_target in zip(path, path[1:])
            ]
            completed = target == str(next_private["goal_square"])
            if completed:
                reason = "goal_reached"

    observation = {
        "move": normalized_move,
        "result": "accepted" if accepted else "rejected",
    }
    if not accepted:
        next_private["rejected_moves"] = int(next_private["rejected_moves"]) + 1
        next_public["rejected_moves"] = int(next_public["rejected_moves"]) + 1
    observations = [
        *list(next_private.get("recent_observations") or []),
        observation,
    ][-RECENT_OBSERVATION_LIMIT:]
    next_private["recent_observations"] = observations
    next_public["recent_observations"] = deepcopy(observations)
    next_public["board"] = _public_board(
        current_square=str(next_private["current_square"]),
        goal_square=str(next_private["goal_square"]),
        blockers=tuple(str(item) for item in next_private["blockers"]),
    )

    if completed:
        shortest_length = int(next_private["initial_shortest_path_length"])
        accepted_moves = int(next_private["accepted_moves"])
        rejected_moves = int(next_private["rejected_moves"])
        efficient = (
            accepted_moves <= shortest_length + 1
            and rejected_moves <= max(1, shortest_length // 2)
        )
        evaluation_state = {
            "correct": True,
            "completed": True,
            "efficient": efficient,
            "accepted_moves": accepted_moves,
            "rejected_moves": rejected_moves,
            "shortest_path_length": shortest_length,
        }
        message = "Ход принят. Цель достигнута; задача завершена."
    elif accepted:
        message = "Ход принят. Позиция обновлена."
    else:
        message = "Ход невозможен. Позиция не изменилась."

    return PenultimaTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=accepted,
        completed=completed,
        reason=reason,
        message=message,
        normalized_move=normalized_move,
        evaluation_state=evaluation_state,
    )
