"""DSL-backed Geometry Zendo v2."""

from __future__ import annotations

import random
from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from ..core.rule_dsl import (
    actual_information_gain,
    filter_version_space,
    information_gain,
    pick_probe_by_entropy,
)
from ..core.rule_space import DEFAULT_DSL_VERSION, RuleSpace, get_rule_space
from .atlas import (
    CARD_COORDINATES,
    GEO_ZENDO_FAMILY,
    MiniGraph,
    _normalize_edges,
    _parse_boolean_sequence,
    _public_state,
    _scene,
)

GENERATOR_VERSION = "geometry-zendo-v2"
PROBE_BUDGET = 5
PROBE_CARD_COUNT = 12
TARGET_COUNT = 8


@dataclass(frozen=True)
class ZendoV2ProbeTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    reason: str
    message: str
    normalized_card_id: str
    telemetry: dict[str, Any] | None


def _graph_key(graph: MiniGraph) -> tuple[object, ...]:
    return graph.points, graph.edges, graph.colors


def _serialize_graph(graph: MiniGraph) -> dict[str, Any]:
    return {
        "points": [list(point) for point in graph.points],
        "edges": [list(edge) for edge in graph.edges],
        "colors": list(graph.colors),
    }


def _deserialize_graph(value: dict[str, Any]) -> MiniGraph:
    return MiniGraph(
        points=tuple(
            (int(point[0]), int(point[1]))
            for point in value["points"]
        ),
        edges=_normalize_edges(
            (int(edge[0]), int(edge[1]))
            for edge in value["edges"]
        ),
        colors=tuple(str(color) for color in value["colors"]),
    )


def _target_truth(
    *,
    graph_truth_mask: int,
    rule_index: int,
) -> bool:
    return bool(graph_truth_mask & (1 << rule_index))


@lru_cache(maxsize=4)
def _universe_graph_truth_masks(dsl_version: str) -> tuple[int, ...]:
    """Transpose cached rule×universe masks into universe×rule masks once."""

    space = get_rule_space(dsl_version)
    masks = [0] * len(space.universe)
    for rule_index, truth_mask in enumerate(space.truth_masks):
        rule_bit = 1 << rule_index
        remaining = truth_mask
        while remaining:
            least_bit = remaining & -remaining
            graph_index = least_bit.bit_length() - 1
            masks[graph_index] |= rule_bit
            remaining ^= least_bit
    return tuple(masks)


def _version_space_after_examples(
    *,
    space: RuleSpace,
    examples: Iterable[tuple[int, bool]],
) -> int:
    version_space = space.all_rules_mask
    for truth_mask, outcome in examples:
        version_space = filter_version_space(
            version_space,
            truth_mask,
            outcome,
            all_rules_mask=space.all_rules_mask,
        )
    return version_space


def _mutations(graph: MiniGraph) -> tuple[MiniGraph, ...]:
    """All one-edge toggles and one-point relocations in stable order."""

    mutations: list[MiniGraph] = []
    edge_set = set(graph.edges)
    for first in range(len(graph.points)):
        for second in range(first + 1, len(graph.points)):
            edge = (first, second)
            next_edges = set(edge_set)
            if edge in next_edges:
                next_edges.remove(edge)
            else:
                next_edges.add(edge)
            mutations.append(
                MiniGraph(
                    points=graph.points,
                    edges=_normalize_edges(next_edges),
                    colors=graph.colors,
                )
            )

    occupied = set(graph.points)
    for index in range(len(graph.points)):
        for coordinate in CARD_COORDINATES:
            if coordinate in occupied and coordinate != graph.points[index]:
                continue
            if coordinate == graph.points[index]:
                continue
            next_points = list(graph.points)
            next_points[index] = coordinate
            mutations.append(
                MiniGraph(
                    points=tuple(next_points),
                    edges=graph.edges,
                    colors=graph.colors,
                )
            )
    unique: dict[tuple[object, ...], MiniGraph] = {}
    for mutation in mutations:
        unique.setdefault(_graph_key(mutation), mutation)
    return tuple(unique.values())


def _near_miss_targets(
    *,
    rng: random.Random,
    space: RuleSpace,
    rule_index: int,
    positive_examples: list[MiniGraph],
    forbidden: set[tuple[object, ...]],
) -> list[MiniGraph] | None:
    toggled: list[MiniGraph] = []
    unchanged: list[MiniGraph] = []
    seen = set(forbidden)
    for example in positive_examples:
        candidates = list(_mutations(example))
        rng.shuffle(candidates)
        for candidate in candidates:
            key = _graph_key(candidate)
            if key in seen:
                continue
            seen.add(key)
            truth = space.rules[rule_index].evaluate(candidate)
            (unchanged if truth else toggled).append(candidate)
    if len(toggled) < 4 or len(unchanged) < 4:
        return None
    selected = [*rng.sample(toggled, 4), *rng.sample(unchanged, 4)]
    rng.shuffle(selected)
    return selected


def _select_material(
    *,
    rng: random.Random,
    space: RuleSpace,
    difficulty: int,
) -> tuple[
    int,
    list[MiniGraph],
    list[bool],
    list[MiniGraph],
    list[int],
    list[MiniGraph],
    int,
]:
    pool = list(space.universe)
    pool_masks = list(_universe_graph_truth_masks(space.dsl_version))
    candidate_rules = list(space.indices_for_difficulty(difficulty))
    rng.shuffle(candidate_rules)

    for rule_index in candidate_rules:
        positives = [
            index
            for index, mask in enumerate(pool_masks)
            if _target_truth(graph_truth_mask=mask, rule_index=rule_index)
        ]
        negatives = [
            index
            for index, mask in enumerate(pool_masks)
            if not _target_truth(graph_truth_mask=mask, rule_index=rule_index)
        ]
        if len(positives) < 2 or len(negatives) < 2:
            continue
        for _ in range(160):
            selected_indices = [
                *rng.sample(positives, 2),
                *rng.sample(negatives, 2),
            ]
            example_observations = [
                (
                    pool_masks[index],
                    index in positives,
                )
                for index in selected_indices
            ]
            version_space = _version_space_after_examples(
                space=space,
                examples=example_observations,
            )
            if not 8 <= version_space.bit_count() <= 64:
                continue
            examples = [pool[index] for index in selected_indices]
            example_labels = [index in positives for index in selected_indices]
            forbidden = {_graph_key(graph) for graph in examples}
            targets = _near_miss_targets(
                rng=rng,
                space=space,
                rule_index=rule_index,
                positive_examples=[
                    graph
                    for graph, label in zip(
                        examples,
                        example_labels,
                        strict=True,
                    )
                    if label
                ],
                forbidden=forbidden,
            )
            if targets is None:
                continue
            forbidden.update(_graph_key(graph) for graph in targets)
            remaining = [
                (graph, truth_mask)
                for graph, truth_mask in zip(pool, pool_masks, strict=True)
                if _graph_key(graph) not in forbidden
            ]
            ranked = sorted(
                remaining,
                key=lambda item: (
                    -information_gain(version_space, item[1]),
                    _graph_key(item[0]),
                ),
            )
            selected_probes = ranked[:PROBE_CARD_COUNT]
            probes = [graph for graph, _mask in selected_probes]
            probe_masks = [mask for _graph, mask in selected_probes]
            if len(probes) != PROBE_CARD_COUNT:
                continue
            return (
                rule_index,
                examples,
                example_labels,
                probes,
                probe_masks,
                targets,
                version_space,
            )
    raise RuntimeError(
        f"Unable to generate Geometry Zendo v2 at difficulty {difficulty}"
    )


def generate_geo_zendo_v2_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("Geometry Zendo v2 difficulty must be from 1 to 5")
    rng = random.Random(seed)
    space = get_rule_space(DEFAULT_DSL_VERSION)
    (
        rule_index,
        examples,
        example_labels,
        probes,
        probe_masks,
        targets,
        version_space,
    ) = _select_material(
        rng=rng,
        space=space,
        difficulty=difficulty,
    )

    example_cards = [
        (f"E{index:02d}", graph)
        for index, graph in enumerate(examples, start=1)
    ]
    probe_cards = [
        (f"P{index:02d}", graph)
        for index, graph in enumerate(probes, start=1)
    ]
    target_cards = [
        (f"T{index:02d}", graph)
        for index, graph in enumerate(targets, start=1)
    ]
    target_answers = [
        space.rules[rule_index].evaluate(graph)
        for graph in targets
    ]
    public = _public_state(
        family=GEO_ZENDO_FAMILY,
        variant="classify_hidden_geometric_rule_v2",
        prompt=(
            "Конфигурации подчиняются скрытому правилу. Изучите два "
            "положительных и два отрицательных примера. Можно проверить до "
            "пяти карточек, затем классифицируйте восемь целей по порядку."
        ),
        scene=_scene(
            graphs=[
                *[
                    (card_id, graph, "violet")
                    for card_id, graph in example_cards
                ],
                *[
                    (card_id, graph, "violet")
                    for card_id, graph in probe_cards
                ],
                *[
                    (card_id, graph, "violet")
                    for card_id, graph in target_cards
                ],
            ]
        ),
        content={
            "examples": [
                {
                    "card_id": card_id,
                    "classification": "positive" if label else "negative",
                }
                for (card_id, _graph), label in zip(
                    example_cards,
                    example_labels,
                    strict=True,
                )
            ],
            "probe_cards": [
                {"card_id": card_id, "used": False}
                for card_id, _graph in probe_cards
            ],
            "targets": [
                {"card_id": card_id, "position": index}
                for index, (card_id, _graph) in enumerate(
                    target_cards,
                    start=1,
                )
            ],
            "probe_budget": PROBE_BUDGET,
            "probes_remaining": PROBE_BUDGET,
            "probe_observations": [],
        },
        mode="probe_then_answer",
        commands=["/test <card_id>", "/answer <да/нет ...>"],
        response_hint=(
            "Ответьте восемью значениями в порядке целей: "
            "/answer да нет да нет да нет да нет."
        ),
    )
    public["dsl_version"] = DEFAULT_DSL_VERSION
    private = {
        "family": GEO_ZENDO_FAMILY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": difficulty,
        "dsl_version": DEFAULT_DSL_VERSION,
        "rule_index": rule_index,
        "version_space": version_space,
        "version_space_after_examples": version_space,
        "probe_cards": {
            card_id: _serialize_graph(graph)
            for card_id, graph in probe_cards
        },
        "probe_truth_masks": {
            card_id: truth_mask
            for (card_id, _graph), truth_mask in zip(
                probe_cards,
                probe_masks,
                strict=True,
            )
        },
        "used_probe_card_ids": [],
        "probe_budget": PROBE_BUDGET,
        "probes_remaining": PROBE_BUDGET,
        "target_card_ids": [
            card_id for card_id, _graph in target_cards
        ],
        "target_answers": target_answers,
    }
    return public, private


def transition_geo_zendo_v2_probe(
    *,
    card_id: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> ZendoV2ProbeTransition:
    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    normalized = card_id.strip().upper()
    probe_cards = next_private.get("probe_cards")
    probe_truth_masks = next_private.get("probe_truth_masks")
    used = [
        str(value)
        for value in next_private.get("used_probe_card_ids", [])
    ]
    if (
        not isinstance(probe_cards, dict)
        or not isinstance(probe_truth_masks, dict)
        or normalized not in probe_cards
        or normalized not in probe_truth_masks
    ):
        return ZendoV2ProbeTransition(
            next_public,
            next_private,
            False,
            "unknown_probe_card",
            "Такой карточки нет среди доступных для проверки.",
            normalized,
            None,
        )
    if normalized in used:
        return ZendoV2ProbeTransition(
            next_public,
            next_private,
            False,
            "probe_already_used",
            "Эта карточка уже была проверена.",
            normalized,
            None,
        )
    if int(next_private.get("probes_remaining") or 0) <= 0:
        return ZendoV2ProbeTransition(
            next_public,
            next_private,
            False,
            "probe_budget_exhausted",
            "Лимит проверок исчерпан.",
            normalized,
            None,
        )

    space = get_rule_space(str(next_private["dsl_version"]))
    rule_index = int(next_private["rule_index"])
    before = int(next_private["version_space"])
    available_ids = [
        candidate_id
        for candidate_id in sorted(probe_cards)
        if candidate_id not in used
    ]
    candidate_graphs = [
        _deserialize_graph(probe_cards[candidate_id])
        for candidate_id in available_ids
    ]
    candidate_masks = [
        int(probe_truth_masks[candidate_id])
        for candidate_id in available_ids
    ]
    best = pick_probe_by_entropy(
        candidates=candidate_graphs,
        rules=space.rules,
        version_space=before,
        candidate_truth_masks=candidate_masks,
    )
    graph_truth_mask = int(probe_truth_masks[normalized])
    outcome = _target_truth(
        graph_truth_mask=graph_truth_mask,
        rule_index=rule_index,
    )
    after = filter_version_space(
        before,
        graph_truth_mask,
        outcome,
        all_rules_mask=space.all_rules_mask,
    )
    telemetry = {
        "vs_size_before": before.bit_count(),
        "vs_size_after": after.bit_count(),
        "gain_bits_actual": actual_information_gain(before, after),
        "gain_bits_best": best.gain_bits if best is not None else 0.0,
    }
    next_private["version_space"] = after
    next_private["used_probe_card_ids"] = [*used, normalized]
    next_private["probes_remaining"] = int(
        next_private["probes_remaining"]
    ) - 1
    content = next_public["content"]
    content["probes_remaining"] = int(content["probes_remaining"]) - 1
    for item in content["probe_cards"]:
        if item["card_id"] == normalized:
            item["used"] = True
            break
    content["probe_observations"].append(
        {
            "card_id": normalized,
            "classification": "positive" if outcome else "negative",
        }
    )
    return ZendoV2ProbeTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=True,
        reason="accepted",
        message=(
            f"Карточка {normalized}: "
            f"{'подходит' if outcome else 'не подходит'}."
        ),
        normalized_card_id=normalized,
        telemetry=telemetry,
    )


def evaluate_geo_zendo_v2_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    expected = [bool(value) for value in private_state["target_answers"]]
    parsed = _parse_boolean_sequence(answer)
    valid = parsed is not None and len(parsed) == len(expected)
    correct_count = (
        sum(
            submitted == expected_value
            for submitted, expected_value in zip(
                parsed,
                expected,
                strict=True,
            )
        )
        if valid and parsed is not None
        else 0
    )
    accuracy = correct_count / len(expected)
    unused_probes = int(private_state.get("probes_remaining") or 0)
    zendo_score = (
        max(0.0, accuracy - 0.5)
        * 2
        * (1 + 0.05 * unused_probes)
    )
    exact = bool(valid and correct_count == len(expected))
    return {
        "correct": exact,
        "parsed": valid,
        "submitted_sequence": parsed if valid else None,
        "target_count": len(expected),
        "correct_count": correct_count,
        "accuracy": accuracy,
        "unused_probes": unused_probes,
        "zendo_score": zendo_score,
        "continuous_score": min(1.0, zendo_score),
        "efficient": exact and unused_probes > 0,
        "evidence": 1 if exact else -1,
    }


__all__ = [
    "GENERATOR_VERSION",
    "PROBE_BUDGET",
    "TARGET_COUNT",
    "ZendoV2ProbeTransition",
    "evaluate_geo_zendo_v2_answer",
    "generate_geo_zendo_v2_task",
    "transition_geo_zendo_v2_probe",
]
