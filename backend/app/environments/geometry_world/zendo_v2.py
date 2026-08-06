"""DSL-backed Geometry Zendo v2 on top of the shared Zendo engine."""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..core.rule_dsl import GRAPH_ATOMS
from ..core.rule_space import DEFAULT_DSL_VERSION, get_rule_space
from ..core.zendo_engine import (
    PROBE_BUDGET,
    PROBE_CARD_COUNT,
    TARGET_COUNT,
    evaluate_zendo_answer,
    rule_hint_category,
    select_material,
    transition_zendo_hint,
    transition_zendo_probe,
    transpose_truth_masks,
)

from .atlas import GEO_ZENDO_FAMILY, _public_state, _scene
from .universe import graph_key, graph_mutations, serialize_graph

GENERATOR_VERSION = "geometry-zendo-v2"

GRAPH_ATOM_DESCRIPTIONS = {
    "vertex_count_even": "чётное число вершин",
    "edge_count_even": "чётное число рёбер",
    "edges_at_least_vertices": "рёбер не меньше, чем вершин",
    "density_at_least_half": "рёбер не меньше половины возможных",
    "all_degrees_even": "степени всех вершин чётны",
    "exactly_two_odd_degrees": "ровно две вершины нечётной степени",
    "max_degree_at_least_three": "есть вершина степени не меньше 3",
    "has_isolated_vertex": "есть изолированная вершина",
    "has_isolated_point": "есть изолированная вершина",
    "has_leaf": "есть висячая вершина (степень 1)",
    "connected": "граф связен",
    "has_triangle": "есть треугольник",
    "has_cycle": "есть цикл",
    "bipartite": "граф двудольный",
    "has_crossing": "есть пересекающиеся на рисунке рёбра",
}

GRAPH_ATOM_HINT_CATEGORIES = {
    "vertex_count_even": "count",
    "edge_count_even": "count",
    "edges_at_least_vertices": "count",
    "density_at_least_half": "count",
    "all_degrees_even": "count",
    "exactly_two_odd_degrees": "count",
    "max_degree_at_least_three": "count",
    "has_isolated_vertex": "connectivity",
    "has_isolated_point": "connectivity",
    "has_leaf": "connectivity",
    "connected": "connectivity",
    "has_triangle": "connectivity",
    "has_cycle": "connectivity",
    "bipartite": "connectivity",
    "has_crossing": "arrangement",
}


@dataclass(frozen=True)
class ZendoV2ProbeTransition:
    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    reason: str
    message: str
    normalized_card_id: str
    telemetry: dict[str, Any] | None


def generate_geo_zendo_v2_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError("Geometry Zendo v2 difficulty must be from 1 to 5")
    rng = random.Random(seed)
    space = get_rule_space(DEFAULT_DSL_VERSION)
    material = select_material(
        rng=rng,
        difficulty=difficulty,
        pool=space.universe,
        pool_masks=_universe_graph_truth_masks(space.dsl_version),
        rules=space.rules,
        atoms=GRAPH_ATOMS,
        all_rules_mask=space.all_rules_mask,
        difficulty_rule_indices=space.indices_for_difficulty(difficulty),
        mutations=graph_mutations,
        object_key=graph_key,
    )

    example_cards = [
        (f"E{index:02d}", graph)
        for index, graph in enumerate(material.examples, start=1)
    ]
    probe_cards = [
        (f"P{index:02d}", graph)
        for index, graph in enumerate(material.probes, start=1)
    ]
    target_cards = [
        (f"T{index:02d}", graph)
        for index, graph in enumerate(material.targets, start=1)
    ]
    public = _public_state(
        family=GEO_ZENDO_FAMILY,
        variant="classify_hidden_geometric_rule_v2",
        prompt=(
            "Рассмотрите предложенные конструкции. Было загадано некоторое "
            "утверждение: одни конструкции ему соответствуют, другие — нет. "
            "Предположите, что это за утверждение, и классифицируйте восемь "
            "целевых конструкций по порядку. Перед ответом можно опробовать "
            "несколько конструкций — доступно 5 проб."
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
                    material.example_labels,
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
        "rule_index": material.rule_index,
        "version_space": material.version_space,
        "version_space_after_examples": material.version_space,
        "probe_cards": {
            card_id: serialize_graph(graph)
            for card_id, graph in probe_cards
        },
        "probe_truth_masks": {
            card_id: truth_mask
            for (card_id, _graph), truth_mask in zip(
                probe_cards,
                material.probe_masks,
                strict=True,
            )
        },
        "used_probe_card_ids": [],
        "probe_budget": PROBE_BUDGET,
        "probes_remaining": PROBE_BUDGET,
        "target_card_ids": [
            card_id for card_id, _graph in target_cards
        ],
        "target_answers": material.target_answers,
    }
    return public, private


@lru_cache(maxsize=4)
def _universe_graph_truth_masks(dsl_version: str) -> tuple[int, ...]:
    """Transpose cached rule×universe masks into universe×rule masks once."""

    space = get_rule_space(dsl_version)
    return transpose_truth_masks(space.truth_masks, len(space.universe))


def transition_geo_zendo_v2_hint(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
):
    space = get_rule_space(str(private_state["dsl_version"]))
    category = rule_hint_category(
        space.rules[int(private_state["rule_index"])],
        GRAPH_ATOM_HINT_CATEGORIES,
    )
    return transition_zendo_hint(
        public_state=public_state,
        private_state=private_state,
        category=category,
    )


def transition_geo_zendo_v2_probe(
    *,
    card_id: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> ZendoV2ProbeTransition:
    space = get_rule_space(str(private_state["dsl_version"]))
    transition = transition_zendo_probe(
        card_id=card_id,
        public_state=public_state,
        private_state=private_state,
        all_rules_mask=space.all_rules_mask,
    )
    return ZendoV2ProbeTransition(
        public_state=transition.public_state,
        private_state=transition.private_state,
        accepted=transition.accepted,
        reason=transition.reason,
        message=transition.message,
        normalized_card_id=transition.normalized_card_id,
        telemetry=transition.telemetry,
    )


def evaluate_geo_zendo_v2_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    return evaluate_zendo_answer(answer=answer, private_state=private_state)


__all__ = [
    "GENERATOR_VERSION",
    "GRAPH_ATOM_DESCRIPTIONS",
    "PROBE_BUDGET",
    "PROBE_CARD_COUNT",
    "TARGET_COUNT",
    "ZendoV2ProbeTransition",
    "evaluate_geo_zendo_v2_answer",
    "generate_geo_zendo_v2_task",
    "transition_geo_zendo_v2_hint",
    "transition_geo_zendo_v2_probe",
]
