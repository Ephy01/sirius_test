from __future__ import annotations

import itertools
import random
import re
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Callable, Iterable, Sequence

PUBLIC_KIND = "geometry_atlas"
GENERATOR_VERSION = "geometry-atlas-v1"

GEO_ZENDO_FAMILY = "geo_zendo"
GEO_TRANSFORM_FAMILY = "geo_transform"
GEO_PROBABILITY_FAMILY = "geo_probability"

FAMILY_WEIGHTS = {
    GEO_ZENDO_FAMILY: 40,
    GEO_TRANSFORM_FAMILY: 30,
    GEO_PROBABILITY_FAMILY: 30,
}
SUPPORTED_FAMILIES = frozenset(FAMILY_WEIGHTS)

POINT_LABELS = "ABCDEFGHIJKL"
POINT_COLORS = ("cyan", "plum", "violet")
CARD_COORDINATES = (
    (-3, 0),
    (-2, -2),
    (0, -3),
    (2, -2),
    (3, 0),
    (2, 2),
    (0, 3),
    (-2, 2),
    (0, 0),
)
GRAPH_COORDINATES = (
    (0, 4),
    (3, 3),
    (4, 0),
    (3, -3),
    (0, -4),
    (-3, -3),
    (-4, 0),
    (-3, 3),
)


@dataclass(frozen=True)
class MiniGraph:
    points: tuple[tuple[int, int], ...]
    edges: tuple[tuple[int, int], ...]
    colors: tuple[str, ...]


@dataclass(frozen=True)
class GeometryProbeTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    reason: str
    message: str


@dataclass(frozen=True)
class D4Transform:
    key: str
    label: str
    apply: Callable[[int, int], tuple[int, int]]


def _identity(x: int, y: int) -> tuple[int, int]:
    return x, y


def _rotate_90(x: int, y: int) -> tuple[int, int]:
    return -y, x


def _rotate_180(x: int, y: int) -> tuple[int, int]:
    return -x, -y


def _rotate_270(x: int, y: int) -> tuple[int, int]:
    return y, -x


def _reflect_x(x: int, y: int) -> tuple[int, int]:
    return x, -y


def _reflect_y(x: int, y: int) -> tuple[int, int]:
    return -x, y


def _reflect_main_diagonal(x: int, y: int) -> tuple[int, int]:
    return y, x


def _reflect_anti_diagonal(x: int, y: int) -> tuple[int, int]:
    return -y, -x


D4_TRANSFORMS = (
    D4Transform("identity", "Тождественное преобразование", _identity),
    D4Transform("rotate_90", "Поворот на 90° против часовой стрелки", _rotate_90),
    D4Transform("rotate_180", "Поворот на 180°", _rotate_180),
    D4Transform("rotate_270", "Поворот на 270° против часовой стрелки", _rotate_270),
    D4Transform("reflect_x", "Отражение относительно оси x", _reflect_x),
    D4Transform("reflect_y", "Отражение относительно оси y", _reflect_y),
    D4Transform("reflect_main", "Отражение относительно прямой y = x", _reflect_main_diagonal),
    D4Transform("reflect_anti", "Отражение относительно прямой y = -x", _reflect_anti_diagonal),
)
D4_BY_KEY = {transform.key: transform for transform in D4_TRANSFORMS}


def _normalize_edges(edges: Iterable[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    return tuple(
        sorted(
            {
                (min(first, second), max(first, second))
                for first, second in edges
                if first != second
            }
        )
    )


def _scene(
    *,
    graphs: Sequence[tuple[str, MiniGraph, str]],
    bounds: tuple[int, int, int, int] = (-4, 4, -4, 4),
) -> dict[str, Any]:
    points: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for group, graph, edge_color in graphs:
        for index, ((x, y), color) in enumerate(
            zip(graph.points, graph.colors, strict=True)
        ):
            label = POINT_LABELS[index]
            points.append(
                {
                    "id": f"{group}:{label}",
                    "group": group,
                    "x": x,
                    "y": y,
                    "label": label,
                    "color": color,
                }
            )
        for edge_index, (first, second) in enumerate(graph.edges, start=1):
            edges.append(
                {
                    "id": f"{group}:E{edge_index}",
                    "group": group,
                    "source": f"{group}:{POINT_LABELS[first]}",
                    "target": f"{group}:{POINT_LABELS[second]}",
                    "color": edge_color,
                }
            )
    min_x, max_x, min_y, max_y = bounds
    return {
        "bounds": {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
        },
        "points": points,
        "edges": edges,
    }


def _public_state(
    *,
    family: str,
    variant: str,
    prompt: str,
    scene: dict[str, Any],
    content: dict[str, Any],
    mode: str,
    commands: list[str],
    response_hint: str,
) -> dict[str, Any]:
    return {
        "kind": PUBLIC_KIND,
        "family": family,
        "variant": variant,
        "prompt": prompt,
        "scene": scene,
        "content": content,
        "interaction": {
            "mode": mode,
            "commands": commands,
        },
        "response_hint": response_hint,
    }


def _adjacency(graph: MiniGraph) -> tuple[frozenset[int], ...]:
    neighbors = [set() for _ in graph.points]
    for first, second in graph.edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    return tuple(frozenset(items) for items in neighbors)


def _is_connected(graph: MiniGraph) -> bool:
    if not graph.points:
        return False
    neighbors = _adjacency(graph)
    reached = {0}
    queue: deque[int] = deque([0])
    while queue:
        current = queue.popleft()
        for neighbor in neighbors[current]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    return len(reached) == len(graph.points)


def _has_triangle(graph: MiniGraph) -> bool:
    edge_set = set(graph.edges)
    return any(
        {(a, b), (a, c), (b, c)} <= edge_set
        for a, b, c in itertools.combinations(range(len(graph.points)), 3)
    )


def _orientation(
    first: tuple[int, int],
    second: tuple[int, int],
    third: tuple[int, int],
) -> int:
    return (
        (second[0] - first[0]) * (third[1] - first[1])
        - (second[1] - first[1]) * (third[0] - first[0])
    )


def _properly_cross(
    first_start: tuple[int, int],
    first_end: tuple[int, int],
    second_start: tuple[int, int],
    second_end: tuple[int, int],
) -> bool:
    first_side = _orientation(first_start, first_end, second_start)
    second_side = _orientation(first_start, first_end, second_end)
    third_side = _orientation(second_start, second_end, first_start)
    fourth_side = _orientation(second_start, second_end, first_end)
    return (
        first_side != 0
        and second_side != 0
        and third_side != 0
        and fourth_side != 0
        and (first_side > 0) != (second_side > 0)
        and (third_side > 0) != (fourth_side > 0)
    )


def _has_crossing(graph: MiniGraph) -> bool:
    for first_edge, second_edge in itertools.combinations(graph.edges, 2):
        if set(first_edge) & set(second_edge):
            continue
        if _properly_cross(
            graph.points[first_edge[0]],
            graph.points[first_edge[1]],
            graph.points[second_edge[0]],
            graph.points[second_edge[1]],
        ):
            return True
    return False


def _edge_count_even(graph: MiniGraph) -> bool:
    return len(graph.edges) % 2 == 0


def _has_isolated_point(graph: MiniGraph) -> bool:
    return any(not neighbors for neighbors in _adjacency(graph))


def _all_degrees_even(graph: MiniGraph) -> bool:
    return all(len(neighbors) % 2 == 0 for neighbors in _adjacency(graph))


ZENDO_RULES: dict[str, Callable[[MiniGraph], bool]] = {
    "edge_count_even": _edge_count_even,
    "connected": _is_connected,
    "has_triangle": _has_triangle,
    "has_isolated_point": _has_isolated_point,
    "has_crossing": _has_crossing,
    "all_degrees_even": _all_degrees_even,
}


def _zendo_rule_keys(difficulty: int) -> tuple[str, ...]:
    keys = ["edge_count_even", "connected"]
    if difficulty >= 2:
        keys.extend(("has_triangle", "has_isolated_point"))
    if difficulty >= 3:
        keys.extend(("has_crossing", "all_degrees_even"))
    return tuple(keys)


def _forced_zendo_graphs() -> list[MiniGraph]:
    square = ((-2, -2), (2, -2), (2, 2), (-2, 2))
    crossing = ((-2, -2), (2, 2), (-2, 2), (2, -2))
    triangle_plus_point = ((-2, -2), (2, -2), (0, 2), (0, 0))
    return [
        MiniGraph(square, _normalize_edges(((0, 1), (1, 2), (2, 3))), POINT_COLORS[:1] * 4),
        MiniGraph(
            square,
            _normalize_edges(((0, 1), (1, 2), (2, 3), (3, 0))),
            POINT_COLORS[:1] * 4,
        ),
        MiniGraph(
            triangle_plus_point,
            _normalize_edges(((0, 1), (1, 2), (2, 0))),
            POINT_COLORS[:1] * 4,
        ),
        MiniGraph(
            crossing,
            _normalize_edges(((0, 1), (2, 3))),
            POINT_COLORS[:1] * 4,
        ),
        MiniGraph(
            square,
            _normalize_edges(((0, 1), (0, 2), (0, 3))),
            POINT_COLORS[:1] * 4,
        ),
        MiniGraph(
            square,
            _normalize_edges(((0, 1), (2, 3))),
            POINT_COLORS[:1] * 4,
        ),
        MiniGraph(
            triangle_plus_point,
            _normalize_edges(((0, 1),)),
            POINT_COLORS[:1] * 4,
        ),
        MiniGraph(
            square,
            _normalize_edges(
                ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))
            ),
            POINT_COLORS[:1] * 4,
        ),
    ]


def _random_zendo_graph(rng: random.Random) -> MiniGraph:
    point_count = rng.randint(4, 6)
    points = tuple(rng.sample(CARD_COORDINATES, point_count))
    possible_edges = list(itertools.combinations(range(point_count), 2))
    edge_count = rng.randint(1, max(1, len(possible_edges) - 1))
    edges = _normalize_edges(rng.sample(possible_edges, edge_count))
    colors = tuple(rng.choice(POINT_COLORS) for _ in range(point_count))
    return MiniGraph(points, edges, colors)


def _zendo_card_pool(rng: random.Random) -> list[tuple[str, MiniGraph]]:
    graphs = _forced_zendo_graphs()
    for point_count in range(3, 7):
        for _ in range(4):
            points = tuple(rng.sample(CARD_COORDINATES, point_count))
            cycle_edges = _normalize_edges(
                (index, (index + 1) % point_count)
                for index in range(point_count)
            )
            graphs.append(
                MiniGraph(
                    points=points,
                    edges=cycle_edges,
                    colors=tuple(
                        rng.choice(POINT_COLORS)
                        for _index in range(point_count)
                    ),
                )
            )
    graphs.extend(_random_zendo_graph(rng) for _ in range(88))
    return [(f"C{index:02d}", graph) for index, graph in enumerate(graphs, start=1)]


def _consistent_zendo_rules(
    *,
    examples: Sequence[tuple[str, MiniGraph]],
    target_rule: str,
    available_rules: Sequence[str],
) -> tuple[str, ...]:
    target_classifier = ZENDO_RULES[target_rule]
    return tuple(
        rule
        for rule in available_rules
        if all(
            ZENDO_RULES[rule](graph) == target_classifier(graph)
            for _card_id, graph in examples
        )
    )


def _select_zendo_material(
    *,
    rng: random.Random,
    pool: list[tuple[str, MiniGraph]],
    target_rule: str,
    available_rules: tuple[str, ...],
    target_count: int,
) -> tuple[
    list[tuple[str, MiniGraph]],
    list[tuple[str, MiniGraph]],
    list[tuple[str, MiniGraph]],
    int,
    tuple[str, ...],
]:
    classifier = ZENDO_RULES[target_rule]
    positives = [card for card in pool if classifier(card[1])]
    negatives = [card for card in pool if not classifier(card[1])]
    if len(positives) < 4 or len(negatives) < 4:
        raise RuntimeError(f"Insufficient Zendo material for rule {target_rule!r}")

    selected_examples: list[tuple[str, MiniGraph]] | None = None
    selected_probes: list[tuple[str, MiniGraph]] | None = None
    selected_version_space: tuple[str, ...] = ()
    probe_budget = 2

    for _ in range(640):
        examples = rng.sample(positives, 2) + rng.sample(negatives, 2)
        if len({card_id for card_id, _graph in examples}) != 4:
            continue
        version_space = _consistent_zendo_rules(
            examples=examples,
            target_rule=target_rule,
            available_rules=available_rules,
        )
        if not 2 <= len(version_space) <= 4:
            continue
        used_ids = {card_id for card_id, _graph in examples}
        remaining = [card for card in pool if card[0] not in used_ids]
        alternatives = [rule for rule in version_space if rule != target_rule]
        rng.shuffle(remaining)
        distinguishing_pair: tuple[
            tuple[str, MiniGraph],
            tuple[str, MiniGraph],
        ] | None = None
        for first, second in itertools.combinations(remaining[:36], 2):
            if all(
                ZENDO_RULES[target_rule](first[1]) != ZENDO_RULES[alternative](first[1])
                or ZENDO_RULES[target_rule](second[1])
                != ZENDO_RULES[alternative](second[1])
                for alternative in alternatives
            ):
                distinguishing_pair = (first, second)
                break
        if distinguishing_pair is None:
            continue
        extra = next(
            card
            for card in remaining
            if card[0] not in {item[0] for item in distinguishing_pair}
        )
        selected_examples = examples
        selected_probes = [*distinguishing_pair, extra]
        selected_version_space = version_space
        break

    if selected_examples is None or selected_probes is None:
        best_examples: list[tuple[str, MiniGraph]] | None = None
        best_version_space: tuple[str, ...] = tuple(available_rules)
        for _ in range(320):
            examples = rng.sample(positives, 2) + rng.sample(negatives, 2)
            version_space = _consistent_zendo_rules(
                examples=examples,
                target_rule=target_rule,
                available_rules=available_rules,
            )
            if len(version_space) < len(best_version_space):
                best_examples = examples
                best_version_space = version_space
            if version_space == (target_rule,):
                break
        selected_examples = best_examples or (rng.sample(positives, 2) + rng.sample(negatives, 2))
        used_ids = {card_id for card_id, _graph in selected_examples}
        selected_probes = rng.sample(
            [card for card in pool if card[0] not in used_ids],
            3,
        )
        selected_version_space = best_version_space

    excluded_ids = {
        card_id
        for card_id, _graph in [*selected_examples, *selected_probes]
    }
    remaining_positives = [
        card for card in positives if card[0] not in excluded_ids
    ]
    remaining_negatives = [
        card for card in negatives if card[0] not in excluded_ids
    ]
    targets = [rng.choice(remaining_positives), rng.choice(remaining_negatives)]
    if target_count == 3:
        excluded_target_ids = {card_id for card_id, _graph in targets}
        remaining = [
            card
            for card in pool
            if card[0] not in excluded_ids | excluded_target_ids
        ]
        targets.append(rng.choice(remaining))
    rng.shuffle(selected_examples)
    rng.shuffle(selected_probes)
    rng.shuffle(targets)
    return (
        selected_examples,
        selected_probes,
        targets,
        probe_budget,
        selected_version_space,
    )


def generate_geo_zendo_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if difficulty < 1:
        raise ValueError("difficulty must be at least 1")
    rng = random.Random(seed)
    available_rules = _zendo_rule_keys(difficulty)
    target_rule = rng.choice(available_rules)
    pool = _zendo_card_pool(rng)
    target_count = 2 if difficulty <= 2 else 3
    examples, probes, targets, probe_budget, version_space = _select_zendo_material(
        rng=rng,
        pool=pool,
        target_rule=target_rule,
        available_rules=available_rules,
        target_count=target_count,
    )
    classifier = ZENDO_RULES[target_rule]
    relevant_cards = [*examples, *probes, *targets]
    public_scene = _scene(
        graphs=[
            (card_id, graph, "violet")
            for card_id, graph in relevant_cards
        ]
    )
    target_ids = [card_id for card_id, _graph in targets]
    probe_ids = [card_id for card_id, _graph in probes]
    truth_by_card = {
        card_id: classifier(graph)
        for card_id, graph in relevant_cards
    }
    public = _public_state(
        family=GEO_ZENDO_FAMILY,
        variant="classify_hidden_geometric_rule",
        prompt=(
            "Рассмотрите предложенные конструкции. Было загадано некоторое "
            "утверждение: одни конструкции ему соответствуют, другие — нет. "
            "Предположите, что это за утверждение, и классифицируйте "
            "целевые конструкции по порядку. Перед ответом можно опробовать "
            "несколько конструкций — число проб ограничено."
        ),
        scene=public_scene,
        content={
            "examples": [
                {
                    "card_id": card_id,
                    "classification": (
                        "positive" if truth_by_card[card_id] else "negative"
                    ),
                }
                for card_id, _graph in examples
            ],
            "probe_cards": [
                {"card_id": card_id, "used": False}
                for card_id in probe_ids
            ],
            "targets": [
                {"card_id": card_id, "position": index}
                for index, card_id in enumerate(target_ids, start=1)
            ],
            "probe_budget": probe_budget,
            "probes_remaining": probe_budget,
            "probe_observations": [],
        },
        mode="probe_then_answer",
        commands=["/probe <card_id>", "/answer <да/нет ...>"],
        response_hint=(
            "Ответьте одной последовательностью в порядке целей, "
            "например: /answer да нет да."
        ),
    )
    private = {
        "family": GEO_ZENDO_FAMILY,
        "variant": "classify_hidden_geometric_rule",
        "difficulty": difficulty,
        "rule_key": target_rule,
        "available_rule_keys": list(available_rules),
        "consistent_rule_keys_after_examples": list(version_space),
        "truth_by_card": truth_by_card,
        "probe_card_ids": probe_ids,
        "used_probe_card_ids": [],
        "probe_budget": probe_budget,
        "probes_remaining": probe_budget,
        "target_card_ids": target_ids,
        "target_answers": [truth_by_card[card_id] for card_id in target_ids],
    }
    return public, private


def transition_geo_zendo_probe(
    *,
    card_id: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> GeometryProbeTransition:
    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    normalized_card_id = card_id.strip().upper()

    if (
        next_public.get("family") != GEO_ZENDO_FAMILY
        or next_private.get("family") != GEO_ZENDO_FAMILY
    ):
        return GeometryProbeTransition(
            public_state=next_public,
            private_state=next_private,
            accepted=False,
            reason="wrong_family",
            message="Проверки карточек доступны только в геометрическом Zendo.",
        )

    probe_ids = [str(item) for item in next_private["probe_card_ids"]]
    used_ids = [str(item) for item in next_private["used_probe_card_ids"]]
    if normalized_card_id not in probe_ids:
        reason = "unknown_probe_card"
        message = "Такой карточки нет среди доступных для проверки."
    elif normalized_card_id in used_ids:
        reason = "probe_already_used"
        message = "Эта карточка уже была проверена."
    elif int(next_private["probes_remaining"]) <= 0:
        reason = "probe_budget_exhausted"
        message = "Лимит проверок исчерпан."
    else:
        truth = bool(next_private["truth_by_card"][normalized_card_id])
        next_private["used_probe_card_ids"].append(normalized_card_id)
        next_private["probes_remaining"] = int(next_private["probes_remaining"]) - 1
        content = next_public["content"]
        content["probes_remaining"] = int(content["probes_remaining"]) - 1
        for item in content["probe_cards"]:
            if item["card_id"] == normalized_card_id:
                item["used"] = True
                break
        classification = "positive" if truth else "negative"
        content["probe_observations"].append(
            {
                "card_id": normalized_card_id,
                "classification": classification,
            }
        )
        return GeometryProbeTransition(
            public_state=next_public,
            private_state=next_private,
            accepted=True,
            reason="accepted",
            message=(
                f"Граф {normalized_card_id}: "
                f"{'подходит' if truth else 'не подходит'}."
            ),
        )

    return GeometryProbeTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=False,
        reason=reason,
        message=message,
    )


def _parse_boolean_sequence(answer: str) -> list[bool] | None:
    normalized = re.sub(
        r"^\s*/?answer\b",
        "",
        answer.strip().casefold(),
    ).strip()
    if not normalized:
        return None
    tokens = [
        token
        for token in re.split(r"[\s,;|/]+", normalized)
        if token
    ]
    true_tokens = {"да", "yes", "y", "1", "true", "+"}
    false_tokens = {"нет", "no", "n", "0", "false", "-"}
    parsed: list[bool] = []
    for token in tokens:
        if token in true_tokens:
            parsed.append(True)
        elif token in false_tokens:
            parsed.append(False)
        else:
            return None
    return parsed


def evaluate_geo_zendo_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    parsed = _parse_boolean_sequence(answer)
    expected = [bool(value) for value in private_state["target_answers"]]
    valid_length = parsed is not None and len(parsed) == len(expected)
    correct = bool(valid_length and parsed == expected)
    evaluation = {
        "correct": correct,
        "parsed": valid_length,
        "submitted_sequence": parsed if valid_length else None,
        "target_count": len(expected),
    }
    if private_state.get("hint_used"):
        evaluation["hint_used"] = True
        evaluation["continuous_score"] = 0.7 if correct else 0.0
    return evaluation


def _transform_keys_for_difficulty(difficulty: int) -> tuple[str, ...]:
    if difficulty <= 1:
        return ("identity", "rotate_90", "rotate_180", "rotate_270")
    if difficulty == 2:
        return (
            "identity",
            "rotate_90",
            "rotate_180",
            "rotate_270",
            "reflect_x",
            "reflect_y",
        )
    return tuple(transform.key for transform in D4_TRANSFORMS)


def _transform_graph(graph: MiniGraph, transform: D4Transform) -> MiniGraph:
    return MiniGraph(
        points=tuple(transform.apply(x, y) for x, y in graph.points),
        edges=graph.edges,
        colors=graph.colors,
    )


def generate_geo_transform_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if difficulty < 1:
        raise ValueError("difficulty must be at least 1")
    rng = random.Random(seed)
    candidate_keys = list(_transform_keys_for_difficulty(difficulty))
    selected_key = rng.choice(candidate_keys)
    selected_transform = D4_BY_KEY[selected_key]

    additional_points = rng.sample(
        [
            coordinate
            for coordinate in CARD_COORDINATES
            if coordinate not in {(1, 2), (0, 0)}
        ],
        2 + min(1, difficulty // 3),
    )
    source_points = ((1, 2), *additional_points)
    source_edges = _normalize_edges(
        (index, index + 1)
        for index in range(len(source_points) - 1)
    )
    source = MiniGraph(
        points=source_points,
        edges=source_edges,
        colors=tuple("cyan" for _ in source_points),
    )
    image = _transform_graph(
        MiniGraph(
            points=source.points,
            edges=source.edges,
            colors=tuple("plum" for _ in source.points),
        ),
        selected_transform,
    )

    rng.shuffle(candidate_keys)
    cards = [
        {
            "id": f"T{index}",
            "label": D4_BY_KEY[key].label,
        }
        for index, key in enumerate(candidate_keys, start=1)
    ]
    card_key_map = {
        card["id"]: key
        for card, key in zip(cards, candidate_keys, strict=True)
    }
    correct_card_id = next(
        card_id
        for card_id, key in card_key_map.items()
        if key == selected_key
    )
    public = _public_state(
        family=GEO_TRANSFORM_FAMILY,
        variant="identify_d4_transform",
        prompt=(
            "К исходной фигуре (source) применено некоторое "
            "преобразование и получен образ (image). Координатная плоскость "
            "и подписи вершин сохраняются. Твоя задача — выбрать это "
            "преобразование."
        ),
        scene=_scene(
            graphs=[
                ("source", source, "cyan"),
                ("image", image, "plum"),
            ]
        ),
        content={
            "source_group": "source",
            "image_group": "image",
            "answer_cards": cards,
        },
        mode="single_answer",
        commands=["/answer <card_id>"],
        response_hint="Например: /answer T3.",
    )
    private = {
        "family": GEO_TRANSFORM_FAMILY,
        "variant": "identify_d4_transform",
        "difficulty": difficulty,
        "transform_key": selected_key,
        "card_key_map": card_key_map,
        "correct_card_id": correct_card_id,
        "source_points": [list(point) for point in source.points],
        "image_points": [list(point) for point in image.points],
    }
    return public, private


def _parse_card_answer(answer: str) -> str | None:
    normalized = re.sub(
        r"^\s*/?answer\b",
        "",
        answer.strip().casefold(),
    ).strip()
    match = re.fullmatch(r"t(\d+)", normalized)
    return f"T{int(match.group(1))}" if match else None


def evaluate_geo_transform_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    submitted_card_id = _parse_card_answer(answer)
    available_cards = set(private_state["card_key_map"])
    parsed = submitted_card_id in available_cards
    return {
        "correct": parsed and submitted_card_id == private_state["correct_card_id"],
        "parsed": parsed,
        "submitted_card_id": submitted_card_id if parsed else None,
    }


def _graph_from_components(
    *,
    points: Sequence[tuple[int, int]],
    edges: Iterable[tuple[int, int]],
    colors: Sequence[str],
) -> MiniGraph:
    return MiniGraph(
        points=tuple(points),
        edges=_normalize_edges(edges),
        colors=tuple(colors),
    )


def _random_connected_graph(
    *,
    rng: random.Random,
    point_count: int,
    extra_edge_count: int,
) -> MiniGraph:
    order = list(range(point_count))
    rng.shuffle(order)
    edges: set[tuple[int, int]] = set()
    for position in range(1, point_count):
        child = order[position]
        parent = rng.choice(order[:position])
        edges.add((min(child, parent), max(child, parent)))
    possible_edges = [
        edge
        for edge in itertools.combinations(range(point_count), 2)
        if edge not in edges
    ]
    edges.update(rng.sample(possible_edges, min(extra_edge_count, len(possible_edges))))
    colors = [rng.choice(POINT_COLORS[:2]) for _ in range(point_count)]
    if len(set(colors)) == 1:
        colors[-1] = POINT_COLORS[1] if colors[0] == POINT_COLORS[0] else POINT_COLORS[0]
    return _graph_from_components(
        points=GRAPH_COORDINATES[:point_count],
        edges=edges,
        colors=colors,
    )


def _probability_event_types(difficulty: int) -> tuple[str, ...]:
    events = ["random_pair_is_edge", "random_vertex_even_degree"]
    if difficulty >= 2:
        events.extend(("random_pair_has_common_neighbor", "random_edge_mixed_colors"))
    if difficulty >= 3:
        events.append("random_triple_is_triangle")
    return tuple(events)


def _event_outcomes(
    graph: MiniGraph,
    event_type: str,
) -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]]:
    vertex_count = len(graph.points)
    edge_set = set(graph.edges)
    neighbors = _adjacency(graph)
    if event_type == "random_pair_is_edge":
        outcomes = tuple(itertools.combinations(range(vertex_count), 2))
        favorable = tuple(outcome for outcome in outcomes if outcome in edge_set)
    elif event_type == "random_vertex_even_degree":
        outcomes = tuple((vertex,) for vertex in range(vertex_count))
        favorable = tuple(
            outcome
            for outcome in outcomes
            if len(neighbors[outcome[0]]) % 2 == 0
        )
    elif event_type == "random_pair_has_common_neighbor":
        outcomes = tuple(itertools.combinations(range(vertex_count), 2))
        favorable = tuple(
            outcome
            for outcome in outcomes
            if neighbors[outcome[0]] & neighbors[outcome[1]]
        )
    elif event_type == "random_edge_mixed_colors":
        outcomes = tuple(graph.edges)
        favorable = tuple(
            edge
            for edge in outcomes
            if graph.colors[edge[0]] != graph.colors[edge[1]]
        )
    elif event_type == "random_triple_is_triangle":
        outcomes = tuple(itertools.combinations(range(vertex_count), 3))
        favorable = tuple(
            (a, b, c)
            for a, b, c in outcomes
            if {
                (min(a, b), max(a, b)),
                (min(a, c), max(a, c)),
                (min(b, c), max(b, c)),
            }
            <= edge_set
        )
    else:
        raise ValueError(f"Unsupported geometry probability event: {event_type!r}")
    return outcomes, favorable


EVENT_DESCRIPTIONS = {
    "random_pair_is_edge": (
        "Равновероятно выбирают две различные вершины. "
        "Найдите вероятность того, что они соединены ребром."
    ),
    "random_vertex_even_degree": (
        "Равновероятно выбирают одну вершину. "
        "Найдите вероятность того, что её степень чётна."
    ),
    "random_pair_has_common_neighbor": (
        "Равновероятно выбирают две различные вершины. "
        "Найдите вероятность того, что у них есть общий сосед."
    ),
    "random_edge_mixed_colors": (
        "Равновероятно выбирают одно из показанных рёбер. "
        "Найдите вероятность того, что его концы имеют разные цвета."
    ),
    "random_triple_is_triangle": (
        "Равновероятно выбирают три различные вершины. "
        "Найдите вероятность того, что они попарно соединены рёбрами."
    ),
}

SAMPLE_SPACE_DESCRIPTIONS = {
    "random_pair_is_edge": "Все неупорядоченные пары различных вершин.",
    "random_vertex_even_degree": "Все вершины графа.",
    "random_pair_has_common_neighbor": "Все неупорядоченные пары различных вершин.",
    "random_edge_mixed_colors": "Все показанные рёбра графа.",
    "random_triple_is_triangle": "Все неупорядоченные тройки различных вершин.",
}


def generate_geo_probability_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if difficulty < 1:
        raise ValueError("difficulty must be at least 1")
    rng = random.Random(seed)
    point_count = min(8, 5 + max(0, difficulty - 1) // 2)
    selected: tuple[MiniGraph, str, tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]] | None = None
    for _ in range(96):
        extra_edges = 1 + rng.randrange(max(2, min(6, difficulty + 1)))
        graph = _random_connected_graph(
            rng=rng,
            point_count=point_count,
            extra_edge_count=extra_edges,
        )
        candidates: list[
            tuple[str, tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]]
        ] = []
        for event_type in _probability_event_types(difficulty):
            outcomes, favorable = _event_outcomes(graph, event_type)
            if 0 < len(favorable) < len(outcomes):
                candidates.append((event_type, outcomes, favorable))
        if candidates:
            event_type, outcomes, favorable = rng.choice(candidates)
            selected = graph, event_type, outcomes, favorable
            break
    if selected is None:
        raise RuntimeError("Could not generate a non-trivial geometry probability task")

    graph, event_type, outcomes, favorable = selected
    probability = Fraction(len(favorable), len(outcomes))
    public = _public_state(
        family=GEO_PROBABILITY_FAMILY,
        variant=event_type,
        prompt=EVENT_DESCRIPTIONS[event_type],
        scene=_scene(graphs=[("graph", graph, "violet")]),
        content={
            "event_description": EVENT_DESCRIPTIONS[event_type],
            "sample_space_description": SAMPLE_SPACE_DESCRIPTIONS[event_type],
            "sample_space_size": len(outcomes),
        },
        mode="single_answer",
        commands=["/answer <p/q>"],
        response_hint="Введите точную дробь, например: /answer 5/12.",
    )
    private = {
        "family": GEO_PROBABILITY_FAMILY,
        "variant": event_type,
        "difficulty": difficulty,
        "point_ids": list(POINT_LABELS[: len(graph.points)]),
        "points": [list(point) for point in graph.points],
        "edges": [
            [POINT_LABELS[first], POINT_LABELS[second]]
            for first, second in graph.edges
        ],
        "colors": {
            POINT_LABELS[index]: color
            for index, color in enumerate(graph.colors)
        },
        "favorable_outcomes": len(favorable),
        "total_outcomes": len(outcomes),
        "probability": {
            "numerator": probability.numerator,
            "denominator": probability.denominator,
        },
    }
    return public, private


def _parse_exact_fraction(answer: str) -> Fraction | None:
    normalized = re.sub(
        r"^\s*/?answer\b",
        "",
        answer.strip().casefold(),
    ).strip()
    fraction_match = re.fullmatch(r"([+-]?\d+)\s*/\s*(\d+)", normalized)
    if fraction_match:
        denominator = int(fraction_match.group(2))
        if denominator == 0:
            return None
        return Fraction(int(fraction_match.group(1)), denominator)
    if re.fullmatch(r"[01]", normalized):
        return Fraction(int(normalized), 1)
    return None


def _private_probability_graph(private_state: dict[str, Any]) -> MiniGraph:
    point_ids = [str(item) for item in private_state["point_ids"]]
    index_by_id = {point_id: index for index, point_id in enumerate(point_ids)}
    return _graph_from_components(
        points=[
            (int(point[0]), int(point[1]))
            for point in private_state["points"]
        ],
        edges=[
            (index_by_id[str(first)], index_by_id[str(second)])
            for first, second in private_state["edges"]
        ],
        colors=[str(private_state["colors"][point_id]) for point_id in point_ids],
    )


def evaluate_geo_probability_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    submitted = _parse_exact_fraction(answer)
    graph = _private_probability_graph(private_state)
    outcomes, favorable = _event_outcomes(graph, str(private_state["variant"]))
    expected = Fraction(len(favorable), len(outcomes))
    in_range = submitted is not None and Fraction(0) <= submitted <= Fraction(1)
    return {
        "correct": bool(in_range and submitted == expected),
        "parsed": in_range,
        "submitted_probability": (
            {
                "numerator": submitted.numerator,
                "denominator": submitted.denominator,
            }
            if in_range and submitted is not None
            else None
        ),
    }


def generate_geometry_atlas_task(
    *,
    family: str,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    generators = {
        GEO_ZENDO_FAMILY: generate_geo_zendo_task,
        GEO_TRANSFORM_FAMILY: generate_geo_transform_task,
        GEO_PROBABILITY_FAMILY: generate_geo_probability_task,
    }
    try:
        generator = generators[family]
    except KeyError as error:
        raise ValueError(f"Unsupported Geometry Atlas family: {family!r}") from error
    return generator(seed=seed, difficulty=difficulty)


def evaluate_geometry_atlas_answer(
    *,
    family: str,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    evaluators = {
        GEO_ZENDO_FAMILY: evaluate_geo_zendo_answer,
        GEO_TRANSFORM_FAMILY: evaluate_geo_transform_answer,
        GEO_PROBABILITY_FAMILY: evaluate_geo_probability_answer,
    }
    try:
        evaluator = evaluators[family]
    except KeyError as error:
        raise ValueError(f"Unsupported Geometry Atlas evaluator: {family!r}") from error
    if private_state.get("family") != family:
        raise ValueError(
            "Geometry Atlas evaluator family does not match the private state"
        )
    return evaluator(answer=answer, private_state=private_state)


__all__ = [
    "FAMILY_WEIGHTS",
    "GENERATOR_VERSION",
    "GEO_PROBABILITY_FAMILY",
    "GEO_TRANSFORM_FAMILY",
    "GEO_ZENDO_FAMILY",
    "GeometryProbeTransition",
    "PUBLIC_KIND",
    "SUPPORTED_FAMILIES",
    "evaluate_geo_probability_answer",
    "evaluate_geo_transform_answer",
    "evaluate_geo_zendo_answer",
    "evaluate_geometry_atlas_answer",
    "generate_geo_probability_task",
    "generate_geo_transform_task",
    "generate_geo_zendo_task",
    "generate_geometry_atlas_task",
    "transition_geo_zendo_probe",
]
