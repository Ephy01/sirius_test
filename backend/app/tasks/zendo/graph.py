"""geo_zendo: hidden rules over small drawn graphs."""

from __future__ import annotations

import random
from dataclasses import replace
from functools import lru_cache
from typing import Any

from ..family import State, TaskFamily, Transition, required_text
from ..graphs import public_state as scene_public_state
from ..graphs import scene
from .engine import (
    PROBE_BUDGET,
    evaluate_zendo_answer,
    reference_answer,
    rule_details,
    rule_hint_category,
    scene_context,
    select_material,
    transition_zendo_hint,
    transition_zendo_probe,
    transpose_truth_masks,
)
from .graph_universe import graph_key, graph_mutations, serialize_graph
from .rule_dsl import GRAPH_ATOMS
from .rule_space import DEFAULT_DSL_VERSION, get_rule_space

FAMILY_KEY = 'geo_zendo'
GENERATOR_VERSION = 'geometry-zendo-v3'

GRAPH_ATOM_DESCRIPTIONS = {
    'vertex_count_even': 'чётное число вершин',
    'edge_count_even': 'чётное число рёбер',
    'edges_at_least_vertices': 'рёбер не меньше, чем вершин',
    'density_at_least_half': 'рёбер не меньше половины возможных',
    'all_degrees_even': 'степени всех вершин чётны',
    'exactly_two_odd_degrees': 'ровно две вершины нечётной степени',
    'max_degree_at_least_three': 'есть вершина степени не меньше 3',
    'has_isolated_vertex': 'есть изолированная вершина',
    'has_isolated_point': 'есть изолированная вершина',
    'has_leaf': 'есть висячая вершина (степень 1)',
    'connected': 'граф связен',
    'has_triangle': 'есть треугольник',
    'has_cycle': 'есть цикл',
    'bipartite': 'граф двудольный',
    'has_crossing': 'есть пересекающиеся на рисунке рёбра',
}

GRAPH_ATOM_HINT_CATEGORIES = {
    'vertex_count_even': 'count',
    'edge_count_even': 'count',
    'edges_at_least_vertices': 'count',
    'density_at_least_half': 'count',
    'all_degrees_even': 'count',
    'exactly_two_odd_degrees': 'count',
    'max_degree_at_least_three': 'count',
    'has_isolated_vertex': 'connectivity',
    'has_isolated_point': 'connectivity',
    'has_leaf': 'connectivity',
    'connected': 'connectivity',
    'has_triangle': 'connectivity',
    'has_cycle': 'connectivity',
    'bipartite': 'connectivity',
    'has_crossing': 'arrangement',
}


def generate_geo_zendo_task(*, seed: int, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if isinstance(difficulty, bool) or not 1 <= difficulty <= 5:
        raise ValueError('Geometry Zendo v2 difficulty must be from 1 to 5')
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

    example_cards = [(f'E{index:02d}', graph) for index, graph in enumerate(material.examples, start=1)]
    probe_cards = [(f'P{index:02d}', graph) for index, graph in enumerate(material.probes, start=1)]
    target_cards = [(f'T{index:02d}', graph) for index, graph in enumerate(material.targets, start=1)]
    public = scene_public_state(
        family=FAMILY_KEY,
        variant='classify_hidden_geometric_rule_v2',
        prompt=(
            'Загадано некоторое свойство для конструкций. Для некоторых '
            'конструкций это свойство выполняется, для некоторых — нет. '
            'Твоя задача — раскрыть это свойство и классифицировать восемь '
            'целевых конструкций по порядку. Доступно 5 подсказок.'
        ),
        scene=scene(
            graphs=[
                *[(card_id, graph, 'violet') for card_id, graph in example_cards],
                *[(card_id, graph, 'violet') for card_id, graph in probe_cards],
                *[(card_id, graph, 'violet') for card_id, graph in target_cards],
            ]
        ),
        content={
            'examples': [
                {'card_id': card_id, 'classification': 'positive' if label else 'negative'}
                for (card_id, _graph), label in zip(example_cards, material.example_labels, strict=True)
            ],
            'probe_cards': [{'card_id': card_id, 'used': False} for card_id, _graph in probe_cards],
            'targets': [
                {'card_id': card_id, 'position': index}
                for index, (card_id, _graph) in enumerate(target_cards, start=1)
            ],
            'probe_budget': PROBE_BUDGET,
            'probes_remaining': PROBE_BUDGET,
            'probe_observations': [],
        },
        mode='probe_then_answer',
        commands=['/test <card_id>', '/answer <да/нет ...>'],
        response_hint=(
            'Ответьте восемью значениями в порядке целей (1 — подходит, 0 — нет): /answer 1 0 1 0 1 0 1 0.'
        ),
    )
    public['dsl_version'] = DEFAULT_DSL_VERSION
    private = {
        'family': FAMILY_KEY,
        'generator_version': GENERATOR_VERSION,
        'difficulty': difficulty,
        'dsl_version': DEFAULT_DSL_VERSION,
        'rule_index': material.rule_index,
        'version_space': material.version_space,
        'version_space_after_examples': material.version_space,
        'probe_cards': {card_id: serialize_graph(graph) for card_id, graph in probe_cards},
        'probe_truth_masks': {
            card_id: truth_mask
            for (card_id, _graph), truth_mask in zip(probe_cards, material.probe_masks, strict=True)
        },
        'used_probe_card_ids': [],
        'probe_budget': PROBE_BUDGET,
        'probes_remaining': PROBE_BUDGET,
        'target_card_ids': [card_id for card_id, _graph in target_cards],
        'target_answers': material.target_answers,
    }
    return public, private


@lru_cache(maxsize=4)
def _universe_graph_truth_masks(dsl_version: str) -> tuple[int, ...]:
    """Transpose cached rule×universe masks into universe×rule masks once."""

    space = get_rule_space(dsl_version)
    return transpose_truth_masks(space.truth_masks, len(space.universe))


def transition_geo_zendo_hint(*, public_state: dict[str, Any], private_state: dict[str, Any]) -> Transition:
    space = get_rule_space(str(private_state['dsl_version']))
    category = rule_hint_category(space.rules[int(private_state['rule_index'])], GRAPH_ATOM_HINT_CATEGORIES)
    return transition_zendo_hint(public_state=public_state, private_state=private_state, category=category)


def transition_geo_zendo_probe(
    *, card_id: str, public_state: dict[str, Any], private_state: dict[str, Any]
) -> Transition:
    space = get_rule_space(str(private_state['dsl_version']))
    transition = transition_zendo_probe(
        card_id=card_id,
        public_state=public_state,
        private_state=private_state,
        all_rules_mask=space.all_rules_mask,
    )
    return replace(transition, message=transition.message.replace('Конструкция', 'Граф', 1))


def evaluate_geo_zendo_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    return evaluate_zendo_answer(answer=answer, private_state=private_state)


def _probe(payload: State, public_state: State, private_state: State) -> Transition:
    return transition_geo_zendo_probe(
        card_id=required_text(payload, 'probe', 'Geometry probe payload must contain a string probe'),
        public_state=public_state,
        private_state=private_state,
    )


def _hint(payload: State, public_state: State, private_state: State) -> Transition:
    return transition_geo_zendo_hint(public_state=public_state, private_state=private_state)


def _debug_details(private_state: State) -> list[str]:
    space = get_rule_space(str(private_state['dsl_version']))
    return rule_details(private_state, space.rules, GRAPH_ATOM_DESCRIPTIONS)


FAMILY = TaskFamily(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    generate=lambda seed, difficulty, context: generate_geo_zendo_task(seed=seed, difficulty=difficulty),
    evaluate=lambda answer, private_state: evaluate_geo_zendo_answer(
        answer=answer, private_state=private_state
    ),
    actions={'probe': _probe, 'hint': _hint},
    probe_action='probe',
    aliases=('geometry_zendo',),
    reference_answer=reference_answer,
    debug_details=_debug_details,
    ai_context=scene_context,
)
