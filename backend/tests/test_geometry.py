from __future__ import annotations

import itertools
from fractions import Fraction

import pytest

from app.tasks import evaluate_task, generate_task
from app.tasks.geo_probability import FAMILY_KEY as GEO_PROBABILITY_FAMILY
from app.tasks.geo_transform import FAMILY_KEY as GEO_TRANSFORM_FAMILY
from app.tasks.geo_transform import GENERATOR_VERSION
from app.tasks.graphs import PUBLIC_KIND

FAMILIES = (GEO_TRANSFORM_FAMILY, GEO_PROBABILITY_FAMILY)


def _generate(family: str, seed: int, difficulty: int) -> tuple[dict, dict]:
    return generate_task(family=family, generator_version=GENERATOR_VERSION, seed=seed, difficulty=difficulty)


def _evaluate(family: str, answer: str, private_state: dict) -> dict:
    return evaluate_task(
        family=family, generator_version=GENERATOR_VERSION, answer=answer, private_state=private_state
    )


PUBLIC_KEYS = {'kind', 'family', 'variant', 'prompt', 'scene', 'content', 'interaction', 'response_hint'}
FORBIDDEN_PUBLIC_KEYS = {
    'rule_key',
    'truth_by_card',
    'target_answers',
    'transform_key',
    'correct_card_id',
    'card_key_map',
    'probability',
    'favorable_outcomes',
    'valid_solution_count',
}


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key for nested_value in value.values() for nested_key in _nested_keys(nested_value)
        }
    if isinstance(value, list):
        return {nested_key for item in value for nested_key in _nested_keys(item)}
    return set()


def _assert_scene_contract(scene: dict) -> None:
    assert set(scene) == {'bounds', 'points', 'edges'}
    assert set(scene['bounds']) == {'min_x', 'max_x', 'min_y', 'max_y'}
    point_ids = set()
    groups = set()
    for point in scene['points']:
        assert set(point) == {'id', 'group', 'x', 'y', 'label', 'color'}
        assert isinstance(point['x'], int)
        assert isinstance(point['y'], int)
        assert point['id'] not in point_ids
        point_ids.add(point['id'])
        groups.add(point['group'])
    edge_ids = set()
    for edge in scene['edges']:
        assert set(edge) == {'id', 'group', 'source', 'target', 'color'}
        assert edge['id'] not in edge_ids
        assert edge['source'] in point_ids
        assert edge['target'] in point_ids
        assert edge['group'] in groups
        edge_ids.add(edge['id'])


def test_family_contract_determinism_and_privacy() -> None:
    assert GENERATOR_VERSION == 'geometry-atlas-v1'

    observed: dict[str, set[str]] = {family: set() for family in FAMILIES}
    for family in FAMILIES:
        for difficulty in (1, 2, 3, 5):
            for seed in range(24):
                public, private = _generate(family, seed, difficulty)
                assert (public, private) == _generate(family, seed, difficulty)
                assert set(public) == PUBLIC_KEYS
                assert public['kind'] == PUBLIC_KIND
                assert public['family'] == family
                assert private['family'] == family
                assert private['difficulty'] == difficulty
                assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
                _assert_scene_contract(public['scene'])
                observed[family].add(public['variant'])

    assert observed[GEO_TRANSFORM_FAMILY] == {'identify_d4_transform'}
    assert len(observed[GEO_PROBABILITY_FAMILY]) >= 4


D4_APPLY = {
    'identity': lambda x, y: (x, y),
    'rotate_90': lambda x, y: (-y, x),
    'rotate_180': lambda x, y: (-x, -y),
    'rotate_270': lambda x, y: (y, -x),
    'reflect_x': lambda x, y: (x, -y),
    'reflect_y': lambda x, y: (-x, y),
    'reflect_main': lambda x, y: (y, x),
    'reflect_anti': lambda x, y: (-y, -x),
}


@pytest.mark.parametrize(('difficulty', 'card_count'), [(1, 4), (2, 6), (3, 8), (6, 8)])
def test_transform_is_exact_unique_and_uses_card_answer(difficulty: int, card_count: int) -> None:
    public, private = _generate(GEO_TRANSFORM_FAMILY, 51 + difficulty, difficulty)
    assert len(public['content']['answer_cards']) == card_count
    source = [tuple(point) for point in private['source_points']]
    image = [tuple(point) for point in private['image_points']]
    apply = D4_APPLY[private['transform_key']]
    assert image == [apply(x, y) for x, y in source]

    candidate_images = {
        key: tuple(D4_APPLY[key](x, y) for x, y in source) for key in private['card_key_map'].values()
    }
    assert len(set(candidate_images.values())) == card_count

    correct_card = private['correct_card_id']
    correct = _evaluate(GEO_TRANSFORM_FAMILY, f'/answer {correct_card.lower()}', private)
    assert correct == {'correct': True, 'parsed': True, 'submitted_card_id': correct_card}
    wrong_card = next(card_id for card_id in private['card_key_map'] if card_id != correct_card)
    wrong = _evaluate(GEO_TRANSFORM_FAMILY, wrong_card, private)
    assert wrong['parsed'] is True
    assert wrong['correct'] is False


def _independent_probability(private: dict) -> tuple[int, int, Fraction]:
    point_ids = private['point_ids']
    edges = {tuple(sorted((first, second))) for first, second in private['edges']}
    neighbors = {point_id: set() for point_id in point_ids}
    for first, second in edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    event = private['variant']
    if event == 'random_pair_is_edge':
        outcomes = list(itertools.combinations(point_ids, 2))
        favorable = [pair for pair in outcomes if tuple(sorted(pair)) in edges]
    elif event == 'random_vertex_even_degree':
        outcomes = [(point_id,) for point_id in point_ids]
        favorable = [outcome for outcome in outcomes if len(neighbors[outcome[0]]) % 2 == 0]
    elif event == 'random_pair_has_common_neighbor':
        outcomes = list(itertools.combinations(point_ids, 2))
        favorable = [pair for pair in outcomes if neighbors[pair[0]] & neighbors[pair[1]]]
    elif event == 'random_edge_mixed_colors':
        outcomes = sorted(edges)
        favorable = [edge for edge in outcomes if private['colors'][edge[0]] != private['colors'][edge[1]]]
    elif event == 'random_triple_is_triangle':
        outcomes = list(itertools.combinations(point_ids, 3))
        favorable = [
            triple
            for triple in outcomes
            if all(tuple(sorted(pair)) in edges for pair in itertools.combinations(triple, 2))
        ]
    else:
        raise AssertionError(f'Unexpected event: {event}')
    return len(favorable), len(outcomes), Fraction(len(favorable), len(outcomes))


def test_probability_uses_individual_graph_and_requires_exact_fraction() -> None:
    observed_events: set[str] = set()
    for difficulty in range(1, 6):
        for seed in range(35):
            public, private = _generate(GEO_PROBABILITY_FAMILY, seed, difficulty)
            favorable, total, exact = _independent_probability(private)
            observed_events.add(private['variant'])
            assert 0 < favorable < total
            assert private['favorable_outcomes'] == favorable
            assert private['total_outcomes'] == total
            assert public['content']['sample_space_size'] == total
            assert private['probability'] == {'numerator': exact.numerator, 'denominator': exact.denominator}

            equivalent_fraction = f'{exact.numerator * 2}/{exact.denominator * 2}'
            correct = _evaluate(GEO_PROBABILITY_FAMILY, f'/answer {equivalent_fraction}', private)
            assert correct['parsed'] is True
            assert correct['correct'] is True
            wrong = _evaluate(GEO_PROBABILITY_FAMILY, '0/1', private)
            assert wrong['parsed'] is True
            assert wrong['correct'] is False
            decimal = _evaluate(GEO_PROBABILITY_FAMILY, str(float(exact)), private)
            assert decimal['parsed'] is False

    assert observed_events == {
        'random_pair_is_edge',
        'random_vertex_even_degree',
        'random_pair_has_common_neighbor',
        'random_edge_mixed_colors',
        'random_triple_is_triangle',
    }


def test_invalid_family_and_difficulty_are_rejected() -> None:
    with pytest.raises(ValueError):
        _generate('unknown', 1, 1)
    for family in FAMILIES:
        with pytest.raises(ValueError, match='difficulty must be at least 1'):
            _generate(family, 1, 0)
