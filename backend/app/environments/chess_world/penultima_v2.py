"""Generated-rule Penultima.

The public mechanics intentionally match ``micro-penultima-v1`` so the same
board scene and command parser can be reused.  The hidden movement rule is no
longer selected from a small published catalogue: it is sampled from a
versioned space of symmetric vector sets.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import deque
from copy import deepcopy
from typing import Any, Iterable

from .penultima import (
    FILES,
    PIECE_NAMES,
    RANKS,
    RECENT_OBSERVATION_LIMIT,
    PenultimaTransition,
    _desired_distance_range,
    _public_board,
    coordinate_to_point,
    parse_move,
    point_to_coordinate,
)

FAMILY_KEY = "penultima"
GENERATOR_VERSION = "micro-penultima-rules-v2"
RULE_SPACE_VERSION = "micro-penultima-rules-v2"
MAX_GENERATION_ATTEMPTS = 256

_DIRECTION_PAIRS = (
    ((1, 0), (-1, 0)),
    ((0, 1), (0, -1)),
    ((1, 1), (-1, -1)),
    ((1, -1), (-1, 1)),
)


def _inside(point: tuple[int, int]) -> bool:
    return 0 <= point[0] < 8 and 0 <= point[1] < 8


def _canonical_rule(rule: dict[str, Any]) -> dict[str, Any]:
    movement = str(rule.get("movement"))
    if movement not in {"leap", "slider"}:
        raise ValueError("Unknown generated Penultima movement")
    raw_vectors = rule.get("vectors")
    if not isinstance(raw_vectors, list):
        raise ValueError("Generated Penultima rule has no vectors")
    vectors = sorted(
        {
            (int(vector[0]), int(vector[1]))
            for vector in raw_vectors
            if isinstance(vector, list) and len(vector) == 2
        }
    )
    if len(vectors) < 4:
        raise ValueError("Generated Penultima rule must have at least four vectors")
    return {
        "movement": movement,
        "vectors": [[x, y] for x, y in vectors],
        "max_distance": max(1, min(3, int(rule.get("max_distance") or 1))),
    }


def _rule_fingerprint(rule: dict[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_rule(rule),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()[:16]


def legal_destinations(
    *,
    square: str,
    rule_spec: dict[str, Any],
    blockers: Iterable[str],
) -> tuple[str, ...]:
    rule = _canonical_rule(rule_spec)
    origin = coordinate_to_point(square)
    blocked = {item.casefold() for item in blockers}
    destinations: set[str] = set()
    for delta_x, delta_y in rule["vectors"]:
        limit = rule["max_distance"] if rule["movement"] == "slider" else 1
        for distance in range(1, limit + 1):
            point = (
                origin[0] + delta_x * distance,
                origin[1] + delta_y * distance,
            )
            if not _inside(point):
                break
            coordinate = point_to_coordinate(point)
            if coordinate in blocked:
                break
            destinations.add(coordinate)
            if rule["movement"] == "leap":
                break
    return tuple(sorted(destinations))


def shortest_path(
    *,
    start: str,
    goal: str,
    rule_spec: dict[str, Any],
    blockers: Iterable[str],
) -> list[str] | None:
    start = start.casefold()
    goal = goal.casefold()
    queue: deque[str] = deque([start])
    parents: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        if current == goal:
            path = [current]
            while parents[current] is not None:
                current = parents[current] or start
                path.append(current)
            return list(reversed(path))
        for destination in legal_destinations(
            square=current,
            rule_spec=rule_spec,
            blockers=blockers,
        ):
            if destination not in parents:
                parents[destination] = current
                queue.append(destination)
    return None


def _distances(
    *,
    start: str,
    rule_spec: dict[str, Any],
    blockers: Iterable[str],
) -> tuple[dict[str, int], dict[str, str | None]]:
    queue: deque[str] = deque([start])
    distances = {start: 0}
    parents: dict[str, str | None] = {start: None}
    while queue:
        current = queue.popleft()
        for destination in legal_destinations(
            square=current,
            rule_spec=rule_spec,
            blockers=blockers,
        ):
            if destination in distances:
                continue
            distances[destination] = distances[current] + 1
            parents[destination] = current
            queue.append(destination)
    return distances, parents


def _path_to(
    goal: str,
    parents: dict[str, str | None],
) -> list[str]:
    path = [goal]
    cursor = goal
    while parents[cursor] is not None:
        cursor = parents[cursor] or cursor
        path.append(cursor)
    return list(reversed(path))


def _sample_rule(
    rng: random.Random,
    difficulty: int,
    exclude_fingerprint: str | None,
) -> dict[str, Any]:
    for _ in range(MAX_GENERATION_ATTEMPTS):
        movement = rng.choice(("leap", "slider"))
        distance = rng.randint(1, min(3, 1 + (difficulty + 1) // 2))
        pair_count = rng.randint(2, min(4, 2 + difficulty // 2))
        selected_pairs = rng.sample(list(_DIRECTION_PAIRS), pair_count)
        unit_vectors = [vector for pair in selected_pairs for vector in pair]
        vectors = (
            [(x * distance, y * distance) for x, y in unit_vectors]
            if movement == "leap"
            else unit_vectors
        )
        rule = {
            "movement": movement,
            "vectors": [[x, y] for x, y in vectors],
            "max_distance": distance if movement == "slider" else 1,
        }
        if _rule_fingerprint(rule) == exclude_fingerprint:
            continue
        distances, _ = _distances(
            start="d4",
            rule_spec=rule,
            blockers=(),
        )
        if len(distances) >= 24:
            return _canonical_rule(rule)
    return {
        "movement": "leap",
        "vectors": [[x, y] for pair in _DIRECTION_PAIRS for x, y in pair],
        "max_distance": 1,
    }


def _select_goal(
    *,
    rng: random.Random,
    start: str,
    rule_spec: dict[str, Any],
    blockers: Iterable[str],
    desired_range: tuple[int, int],
) -> tuple[str, list[str]] | None:
    distances, parents = _distances(
        start=start,
        rule_spec=rule_spec,
        blockers=blockers,
    )
    candidates = [
        square
        for square, distance in distances.items()
        if desired_range[0] <= distance <= desired_range[1]
    ]
    if not candidates:
        return None
    goal = rng.choice(sorted(candidates))
    return goal, _path_to(goal, parents)


def _new_chapter(
    *,
    rng: random.Random,
    difficulty: int,
    desired_range: tuple[int, int],
    exclude_fingerprint: str | None,
) -> tuple[dict[str, Any], tuple[str, ...], str, str, list[str]]:
    squares = [f"{file_name}{rank}" for rank in RANKS for file_name in FILES]
    for _ in range(MAX_GENERATION_ATTEMPTS):
        rule = _sample_rule(rng, difficulty, exclude_fingerprint)
        blocker_count = min(12, 3 + difficulty + rng.randrange(3))
        blockers = tuple(sorted(rng.sample(squares, blocker_count)))
        free = [square for square in squares if square not in blockers]
        start = rng.choice(free)
        if len(
            legal_destinations(
                square=start,
                rule_spec=rule,
                blockers=blockers,
            )
        ) < 2:
            continue
        selected = _select_goal(
            rng=rng,
            start=start,
            rule_spec=rule,
            blockers=blockers,
            desired_range=desired_range,
        )
        if selected is not None:
            goal, path = selected
            return rule, blockers, start, goal, path
    rule = _sample_rule(rng, 1, exclude_fingerprint)
    start = "b2"
    selected = _select_goal(
        rng=rng,
        start=start,
        rule_spec=rule,
        blockers=(),
        desired_range=(1, 8),
    )
    if selected is None:
        raise RuntimeError("Generated Penultima fallback has no goal")
    return rule, (), start, selected[0], selected[1]


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
    previous_distance = generation_context.get("previous_shortest_path_length")
    desired_range = _desired_distance_range(
        difficulty=difficulty,
        branch=branch,
        previous_distance=(
            previous_distance
            if isinstance(previous_distance, int)
            and not isinstance(previous_distance, bool)
            else None
        ),
    )
    preserved = generation_context.get("chapter")
    same_chapter = (
        branch in {"advance", "consolidate", "remediate"}
        and isinstance(preserved, dict)
        and isinstance(preserved.get("rule_spec"), dict)
    )
    if same_chapter:
        rule = _canonical_rule(preserved["rule_spec"])
        blockers = tuple(sorted(str(item) for item in preserved["blockers"]))
        start = str(preserved["current_square"])
        selected = _select_goal(
            rng=rng,
            start=start,
            rule_spec=rule,
            blockers=blockers,
            desired_range=desired_range,
        )
        if selected is None:
            selected = _select_goal(
                rng=rng,
                start=start,
                rule_spec=rule,
                blockers=blockers,
                desired_range=(1, 12),
            )
        if selected is None:
            raise RuntimeError("Preserved generated Penultima chapter is disconnected")
        goal, path = selected
        chapter_id = str(preserved["chapter_id"])
        chapter_stage = int(preserved["chapter_stage"])
        piece_name = str(preserved["piece_name"])
    else:
        rule, blockers, start, goal, path = _new_chapter(
            rng=rng,
            difficulty=difficulty,
            desired_range=desired_range,
            exclude_fingerprint=(
                str(generation_context["exclude_rule_fingerprint"])
                if generation_context.get("exclude_rule_fingerprint")
                else None
            ),
        )
        chapter_id = hashlib.sha256(
            f"{GENERATOR_VERSION}:{seed}:chapter".encode("ascii")
        ).hexdigest()[:16]
        chapter_stage = 1
        piece_name = rng.choice(PIECE_NAMES)

    inherited = generation_context.get("recent_observations")
    observations = (
        deepcopy(inherited[-RECENT_OBSERVATION_LIMIT:])
        if same_chapter and isinstance(inherited, list)
        else []
    )
    shortest_moves = [
        f"{source}{target}" for source, target in zip(path, path[1:])
    ]
    stage_title = {1: "Разведка", 2: "Перенос", 3: "Маршрут"}.get(
        chapter_stage,
        "Маршрут",
    )
    public_state = {
        "kind": "penultima_induction",
        "prompt": (
            f"{stage_title}. Доставьте фигуру «{piece_name}» на клетку {goal}. "
            "Правило движения скрыто и сохраняется в пределах главы. "
            "Предлагайте ходы и восстанавливайте его по ответам системы."
        ),
        "board": _public_board(
            current_square=start,
            goal_square=goal,
            blockers=blockers,
        ),
        "piece_name": piece_name,
        "current_square": start,
        "goal_square": goal,
        "chapter_stage": chapter_stage,
        "stage_title": stage_title,
        "accepted_moves": 0,
        "rejected_moves": 0,
        "recent_observations": observations,
        "response_hint": "Введите ход командой /move a1 b2.",
    }
    private_state = {
        "rule_space_version": RULE_SPACE_VERSION,
        "rule_spec": rule,
        "rule_fingerprint": _rule_fingerprint(rule),
        "blockers": list(blockers),
        "current_square": start,
        "goal_square": goal,
        "initial_square": start,
        "shortest_solution": shortest_moves,
        "initial_shortest_path_length": len(shortest_moves),
        "remaining_shortest_solution": shortest_moves,
        "chapter_id": chapter_id,
        "chapter_stage": chapter_stage,
        "piece_name": piece_name,
        "accepted_moves": 0,
        "rejected_moves": 0,
        "recent_observations": observations,
        "difficulty": difficulty,
        "generation": {
            "parent_task_id": parent_task_id,
            "branch": branch,
            "context_hash": str(generation_context.get("context_hash") or ""),
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
    normalized_move = move.strip().casefold()
    if parsed is None:
        reason = "invalid_format"
    else:
        source, target, normalized_move = parsed
        current = str(next_private["current_square"])
        blockers = tuple(str(item) for item in next_private["blockers"])
        if source != current:
            reason = "wrong_origin"
        elif source == target:
            reason = "same_square"
        elif target in blockers:
            reason = "blocked_destination"
        elif target not in legal_destinations(
            square=current,
            rule_spec=next_private["rule_spec"],
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
                rule_spec=next_private["rule_spec"],
                blockers=blockers,
            )
            if path is None:
                raise RuntimeError("Generated symmetric rule left the goal component")
            next_private["remaining_shortest_solution"] = [
                f"{left}{right}" for left, right in zip(path, path[1:])
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
            "continuous_score": min(
                1.0,
                0.7 + 0.3 * shortest_length / max(shortest_length, accepted_moves),
            ),
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
