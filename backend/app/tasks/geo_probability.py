"""geo_probability: exact probability of a random event on a drawn graph."""

from __future__ import annotations

import itertools
import random
import re
from collections.abc import Iterable, Sequence
from fractions import Fraction
from typing import Any

from .answers import probability_debug_details, probability_reference_answer, strip_answer_command
from .family import State, TaskFamily
from .graphs import (
    GRAPH_COORDINATES,
    POINT_COLORS,
    POINT_LABELS,
    MiniGraph,
    adjacency,
    normalize_edges,
    public_state,
    scene,
    scene_cards,
)

FAMILY_KEY = 'geo_probability'
GENERATOR_VERSION = 'geometry-atlas-v1'


def _graph_from_components(
    *, points: Sequence[tuple[int, int]], edges: Iterable[tuple[int, int]], colors: Sequence[str]
) -> MiniGraph:
    return MiniGraph(points=tuple(points), edges=normalize_edges(edges), colors=tuple(colors))


def _random_connected_graph(*, rng: random.Random, point_count: int, extra_edge_count: int) -> MiniGraph:
    order = list(range(point_count))
    rng.shuffle(order)
    edges: set[tuple[int, int]] = set()
    for position in range(1, point_count):
        child = order[position]
        parent = rng.choice(order[:position])
        edges.add((min(child, parent), max(child, parent)))
    possible_edges = [edge for edge in itertools.combinations(range(point_count), 2) if edge not in edges]
    edges.update(rng.sample(possible_edges, min(extra_edge_count, len(possible_edges))))
    colors = [rng.choice(POINT_COLORS[:2]) for _ in range(point_count)]
    if len(set(colors)) == 1:
        colors[-1] = POINT_COLORS[1] if colors[0] == POINT_COLORS[0] else POINT_COLORS[0]
    return _graph_from_components(points=GRAPH_COORDINATES[:point_count], edges=edges, colors=colors)


def _probability_event_types(difficulty: int) -> tuple[str, ...]:
    events = ['random_pair_is_edge', 'random_vertex_even_degree']
    if difficulty >= 2:
        events.extend(('random_pair_has_common_neighbor', 'random_edge_mixed_colors'))
    if difficulty >= 3:
        events.append('random_triple_is_triangle')
    return tuple(events)


def _event_outcomes(
    graph: MiniGraph, event_type: str
) -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]]:
    vertex_count = len(graph.points)
    edge_set = set(graph.edges)
    neighbors = adjacency(graph)
    if event_type == 'random_pair_is_edge':
        outcomes = tuple(itertools.combinations(range(vertex_count), 2))
        favorable = tuple(outcome for outcome in outcomes if outcome in edge_set)
    elif event_type == 'random_vertex_even_degree':
        outcomes = tuple((vertex,) for vertex in range(vertex_count))
        favorable = tuple(outcome for outcome in outcomes if len(neighbors[outcome[0]]) % 2 == 0)
    elif event_type == 'random_pair_has_common_neighbor':
        outcomes = tuple(itertools.combinations(range(vertex_count), 2))
        favorable = tuple(outcome for outcome in outcomes if neighbors[outcome[0]] & neighbors[outcome[1]])
    elif event_type == 'random_edge_mixed_colors':
        outcomes = tuple(graph.edges)
        favorable = tuple(edge for edge in outcomes if graph.colors[edge[0]] != graph.colors[edge[1]])
    elif event_type == 'random_triple_is_triangle':
        outcomes = tuple(itertools.combinations(range(vertex_count), 3))
        favorable = tuple(
            (a, b, c)
            for a, b, c in outcomes
            if {(min(a, b), max(a, b)), (min(a, c), max(a, c)), (min(b, c), max(b, c))} <= edge_set
        )
    else:
        raise ValueError(f'Unsupported geometry probability event: {event_type!r}')
    return outcomes, favorable


EVENT_DESCRIPTIONS = {
    'random_pair_is_edge': (
        'Равновероятно выбирают две различные вершины. Найдите вероятность того, что они соединены ребром.'
    ),
    'random_vertex_even_degree': (
        'Равновероятно выбирают одну вершину. Найдите вероятность того, что её степень чётна.'
    ),
    'random_pair_has_common_neighbor': (
        'Равновероятно выбирают две различные вершины. Найдите вероятность того, что у них есть общий сосед.'
    ),
    'random_edge_mixed_colors': (
        'Равновероятно выбирают одно из показанных рёбер. '
        'Найдите вероятность того, что его концы имеют разные цвета.'
    ),
    'random_triple_is_triangle': (
        'Равновероятно выбирают три различные вершины. '
        'Найдите вероятность того, что они попарно соединены рёбрами.'
    ),
}

SAMPLE_SPACE_DESCRIPTIONS = {
    'random_pair_is_edge': 'Все неупорядоченные пары различных вершин.',
    'random_vertex_even_degree': 'Все вершины графа.',
    'random_pair_has_common_neighbor': 'Все неупорядоченные пары различных вершин.',
    'random_edge_mixed_colors': 'Все показанные рёбра графа.',
    'random_triple_is_triangle': 'Все неупорядоченные тройки различных вершин.',
}


def generate_geo_probability_task(*, seed: int, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if difficulty < 1:
        raise ValueError('difficulty must be at least 1')
    rng = random.Random(seed)
    point_count = min(8, 5 + max(0, difficulty - 1) // 2)
    selected: tuple[MiniGraph, str, tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]] | None = None
    for _ in range(96):
        extra_edges = 1 + rng.randrange(max(2, min(6, difficulty + 1)))
        graph = _random_connected_graph(rng=rng, point_count=point_count, extra_edge_count=extra_edges)
        candidates: list[tuple[str, tuple[tuple[int, ...], ...], tuple[tuple[int, ...], ...]]] = []
        for event_type in _probability_event_types(difficulty):
            outcomes, favorable = _event_outcomes(graph, event_type)
            if 0 < len(favorable) < len(outcomes):
                candidates.append((event_type, outcomes, favorable))
        if candidates:
            event_type, outcomes, favorable = rng.choice(candidates)
            selected = graph, event_type, outcomes, favorable
            break
    if selected is None:
        raise RuntimeError('Could not generate a non-trivial geometry probability task')

    graph, event_type, outcomes, favorable = selected
    probability = Fraction(len(favorable), len(outcomes))
    public = public_state(
        family=FAMILY_KEY,
        variant=event_type,
        prompt=EVENT_DESCRIPTIONS[event_type],
        scene=scene(graphs=[('graph', graph, 'violet')]),
        content={
            'event_description': EVENT_DESCRIPTIONS[event_type],
            'sample_space_description': SAMPLE_SPACE_DESCRIPTIONS[event_type],
            'sample_space_size': len(outcomes),
        },
        mode='single_answer',
        commands=['/answer <p/q>'],
        response_hint='Введите точную дробь, например: /answer 5/12.',
    )
    private = {
        'family': FAMILY_KEY,
        'variant': event_type,
        'difficulty': difficulty,
        'point_ids': list(POINT_LABELS[: len(graph.points)]),
        'points': [list(point) for point in graph.points],
        'edges': [[POINT_LABELS[first], POINT_LABELS[second]] for first, second in graph.edges],
        'colors': {POINT_LABELS[index]: color for index, color in enumerate(graph.colors)},
        'favorable_outcomes': len(favorable),
        'total_outcomes': len(outcomes),
        'probability': {'numerator': probability.numerator, 'denominator': probability.denominator},
    }
    return public, private


def _parse_exact_fraction(answer: str) -> Fraction | None:
    normalized = strip_answer_command(answer)
    fraction_match = re.fullmatch(r'([+-]?\d+)\s*/\s*(\d+)', normalized)
    if fraction_match:
        denominator = int(fraction_match.group(2))
        if denominator == 0:
            return None
        return Fraction(int(fraction_match.group(1)), denominator)
    if re.fullmatch(r'[01]', normalized):
        return Fraction(int(normalized), 1)
    return None


def _private_probability_graph(private_state: dict[str, Any]) -> MiniGraph:
    point_ids = [str(item) for item in private_state['point_ids']]
    index_by_id = {point_id: index for index, point_id in enumerate(point_ids)}
    return _graph_from_components(
        points=[(int(point[0]), int(point[1])) for point in private_state['points']],
        edges=[
            (index_by_id[str(first)], index_by_id[str(second)]) for first, second in private_state['edges']
        ],
        colors=[str(private_state['colors'][point_id]) for point_id in point_ids],
    )


def evaluate_geo_probability_answer(*, answer: str, private_state: dict[str, Any]) -> dict[str, Any]:
    submitted = _parse_exact_fraction(answer)
    graph = _private_probability_graph(private_state)
    outcomes, favorable = _event_outcomes(graph, str(private_state['variant']))
    expected = Fraction(len(favorable), len(outcomes))
    in_range = submitted is not None and Fraction(0) <= submitted <= Fraction(1)
    return {
        'correct': bool(in_range and submitted == expected),
        'parsed': in_range,
        'submitted_probability': (
            {'numerator': submitted.numerator, 'denominator': submitted.denominator}
            if in_range and submitted is not None
            else None
        ),
    }


def _ai_context(visible_state: State) -> State:
    content = visible_state.get('content') if isinstance(visible_state.get('content'), dict) else {}
    return {
        'figures': [{'id': group, **card} for group, card in sorted(scene_cards(visible_state).items())],
        'eventDescription': content.get('event_description'),
        'sampleSpaceDescription': content.get('sample_space_description'),
        'sampleSpaceSize': content.get('sample_space_size'),
    }


FAMILY = TaskFamily(
    key=FAMILY_KEY,
    version=GENERATOR_VERSION,
    generate=lambda seed, difficulty, context: generate_geo_probability_task(
        seed=seed, difficulty=difficulty
    ),
    evaluate=lambda answer, private_state: evaluate_geo_probability_answer(
        answer=answer, private_state=private_state
    ),
    aliases=('geometry_probability',),
    reference_answer=probability_reference_answer,
    debug_details=probability_debug_details,
    ai_context=_ai_context,
)
