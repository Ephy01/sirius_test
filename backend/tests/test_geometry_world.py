from __future__ import annotations

import itertools
from copy import deepcopy
from fractions import Fraction

import pytest

from app.environments.geometry_world.atlas import (
    FAMILY_WEIGHTS,
    GENERATOR_VERSION,
    GEO_PROBABILITY_FAMILY,
    GEO_TRANSFORM_FAMILY,
    GEO_ZENDO_FAMILY,
    PUBLIC_KIND,
    SUPPORTED_FAMILIES,
    evaluate_geometry_atlas_answer,
    generate_geometry_atlas_task,
    transition_geo_zendo_probe,
)

PUBLIC_KEYS = {
    "kind",
    "family",
    "variant",
    "prompt",
    "scene",
    "content",
    "interaction",
    "response_hint",
}
FORBIDDEN_PUBLIC_KEYS = {
    "rule_key",
    "truth_by_card",
    "target_answers",
    "transform_key",
    "correct_card_id",
    "card_key_map",
    "probability",
    "favorable_outcomes",
    "valid_solution_count",
}


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested_value in value.values()
            for nested_key in _nested_keys(nested_value)
        }
    if isinstance(value, list):
        return {
            nested_key
            for item in value
            for nested_key in _nested_keys(item)
        }
    return set()


def _assert_scene_contract(scene: dict) -> None:
    assert set(scene) == {"bounds", "points", "edges"}
    assert set(scene["bounds"]) == {"min_x", "max_x", "min_y", "max_y"}
    point_ids = set()
    groups = set()
    for point in scene["points"]:
        assert set(point) == {
            "id",
            "group",
            "x",
            "y",
            "label",
            "color",
        }
        assert isinstance(point["x"], int)
        assert isinstance(point["y"], int)
        assert point["id"] not in point_ids
        point_ids.add(point["id"])
        groups.add(point["group"])
    edge_ids = set()
    for edge in scene["edges"]:
        assert set(edge) == {
            "id",
            "group",
            "source",
            "target",
            "color",
        }
        assert edge["id"] not in edge_ids
        assert edge["source"] in point_ids
        assert edge["target"] in point_ids
        assert edge["group"] in groups
        edge_ids.add(edge["id"])


def test_family_contract_weights_determinism_and_privacy() -> None:
    assert GENERATOR_VERSION == "geometry-atlas-v1"
    assert FAMILY_WEIGHTS == {
        GEO_ZENDO_FAMILY: 40,
        GEO_TRANSFORM_FAMILY: 30,
        GEO_PROBABILITY_FAMILY: 30,
    }
    assert sum(FAMILY_WEIGHTS.values()) == 100
    assert set(FAMILY_WEIGHTS) == SUPPORTED_FAMILIES

    observed: dict[str, set[str]] = {
        family: set()
        for family in SUPPORTED_FAMILIES
    }
    for family in sorted(SUPPORTED_FAMILIES):
        for difficulty in (1, 2, 3, 5):
            for seed in range(24):
                public, private = generate_geometry_atlas_task(
                    family=family,
                    seed=seed,
                    difficulty=difficulty,
                )
                assert (public, private) == generate_geometry_atlas_task(
                    family=family,
                    seed=seed,
                    difficulty=difficulty,
                )
                assert set(public) == PUBLIC_KEYS
                assert public["kind"] == PUBLIC_KIND
                assert public["family"] == family
                assert private["family"] == family
                assert private["difficulty"] == difficulty
                assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
                _assert_scene_contract(public["scene"])
                observed[family].add(public["variant"])

    assert observed[GEO_ZENDO_FAMILY] == {
        "classify_hidden_geometric_rule"
    }
    assert observed[GEO_TRANSFORM_FAMILY] == {"identify_d4_transform"}
    assert len(observed[GEO_PROBABILITY_FAMILY]) >= 4


@pytest.mark.parametrize("difficulty", (1, 3, 5))
def test_zendo_examples_targets_probe_transition_and_exact_answer(
    difficulty: int,
) -> None:
    public, private = generate_geometry_atlas_task(
        family=GEO_ZENDO_FAMILY,
        seed=117 + difficulty,
        difficulty=difficulty,
    )
    content = public["content"]
    truth_by_card = private["truth_by_card"]

    assert len(content["examples"]) == 4
    assert sum(
        item["classification"] == "positive"
        for item in content["examples"]
    ) == 2
    assert sum(
        item["classification"] == "negative"
        for item in content["examples"]
    ) == 2
    assert all(
        (item["classification"] == "positive")
        is bool(truth_by_card[item["card_id"]])
        for item in content["examples"]
    )
    assert len(content["probe_cards"]) == 3
    assert content["probe_budget"] == 2
    assert content["probes_remaining"] == 2
    assert len(content["targets"]) == (2 if difficulty <= 2 else 3)
    assert all(set(item) == {"card_id", "position"} for item in content["targets"])

    original_public = deepcopy(public)
    original_private = deepcopy(private)
    first_probe_id = content["probe_cards"][0]["card_id"]
    first_transition = transition_geo_zendo_probe(
        card_id=first_probe_id.lower(),
        public_state=public,
        private_state=private,
    )
    assert first_transition.accepted is True
    assert first_transition.reason == "accepted"
    assert public == original_public
    assert private == original_private
    assert first_transition.public_state["content"]["probes_remaining"] == 1
    assert first_transition.private_state["probes_remaining"] == 1
    observation = first_transition.public_state["content"]["probe_observations"][0]
    assert observation == {
        "card_id": first_probe_id,
        "classification": (
            "positive" if truth_by_card[first_probe_id] else "negative"
        ),
    }

    repeated = transition_geo_zendo_probe(
        card_id=first_probe_id,
        public_state=first_transition.public_state,
        private_state=first_transition.private_state,
    )
    assert repeated.accepted is False
    assert repeated.reason == "probe_already_used"

    second_probe_id = content["probe_cards"][1]["card_id"]
    second_transition = transition_geo_zendo_probe(
        card_id=second_probe_id,
        public_state=first_transition.public_state,
        private_state=first_transition.private_state,
    )
    assert second_transition.accepted is True
    assert second_transition.public_state["content"]["probes_remaining"] == 0

    third_probe_id = content["probe_cards"][2]["card_id"]
    exhausted = transition_geo_zendo_probe(
        card_id=third_probe_id,
        public_state=second_transition.public_state,
        private_state=second_transition.private_state,
    )
    assert exhausted.accepted is False
    assert exhausted.reason == "probe_budget_exhausted"

    expected_tokens = [
        "да" if answer else "нет"
        for answer in private["target_answers"]
    ]
    correct = evaluate_geometry_atlas_answer(
        family=GEO_ZENDO_FAMILY,
        answer=f"/answer {' '.join(expected_tokens)}",
        private_state=private,
    )
    assert correct == {
        "correct": True,
        "parsed": True,
        "submitted_sequence": private["target_answers"],
        "target_count": len(private["target_answers"]),
    }

    wrong_tokens = expected_tokens.copy()
    wrong_tokens[0] = "нет" if wrong_tokens[0] == "да" else "да"
    wrong = evaluate_geometry_atlas_answer(
        family=GEO_ZENDO_FAMILY,
        answer=" ".join(wrong_tokens),
        private_state=private,
    )
    assert wrong["parsed"] is True
    assert wrong["correct"] is False
    assert evaluate_geometry_atlas_answer(
        family=GEO_ZENDO_FAMILY,
        answer="да возможно",
        private_state=private,
    )["parsed"] is False


D4_APPLY = {
    "identity": lambda x, y: (x, y),
    "rotate_90": lambda x, y: (-y, x),
    "rotate_180": lambda x, y: (-x, -y),
    "rotate_270": lambda x, y: (y, -x),
    "reflect_x": lambda x, y: (x, -y),
    "reflect_y": lambda x, y: (-x, y),
    "reflect_main": lambda x, y: (y, x),
    "reflect_anti": lambda x, y: (-y, -x),
}


@pytest.mark.parametrize(
    ("difficulty", "card_count"),
    [(1, 4), (2, 6), (3, 8), (6, 8)],
)
def test_transform_is_exact_unique_and_uses_card_answer(
    difficulty: int,
    card_count: int,
) -> None:
    public, private = generate_geometry_atlas_task(
        family=GEO_TRANSFORM_FAMILY,
        seed=51 + difficulty,
        difficulty=difficulty,
    )
    assert len(public["content"]["answer_cards"]) == card_count
    source = [tuple(point) for point in private["source_points"]]
    image = [tuple(point) for point in private["image_points"]]
    apply = D4_APPLY[private["transform_key"]]
    assert image == [apply(x, y) for x, y in source]

    candidate_images = {
        key: tuple(D4_APPLY[key](x, y) for x, y in source)
        for key in private["card_key_map"].values()
    }
    assert len(set(candidate_images.values())) == card_count

    correct_card = private["correct_card_id"]
    correct = evaluate_geometry_atlas_answer(
        family=GEO_TRANSFORM_FAMILY,
        answer=f"/answer {correct_card.lower()}",
        private_state=private,
    )
    assert correct == {
        "correct": True,
        "parsed": True,
        "submitted_card_id": correct_card,
    }
    wrong_card = next(
        card_id
        for card_id in private["card_key_map"]
        if card_id != correct_card
    )
    wrong = evaluate_geometry_atlas_answer(
        family=GEO_TRANSFORM_FAMILY,
        answer=wrong_card,
        private_state=private,
    )
    assert wrong["parsed"] is True
    assert wrong["correct"] is False


def _independent_probability(private: dict) -> tuple[int, int, Fraction]:
    point_ids = private["point_ids"]
    edges = {
        tuple(sorted((first, second)))
        for first, second in private["edges"]
    }
    neighbors = {point_id: set() for point_id in point_ids}
    for first, second in edges:
        neighbors[first].add(second)
        neighbors[second].add(first)
    event = private["variant"]
    if event == "random_pair_is_edge":
        outcomes = list(itertools.combinations(point_ids, 2))
        favorable = [pair for pair in outcomes if tuple(sorted(pair)) in edges]
    elif event == "random_vertex_even_degree":
        outcomes = [(point_id,) for point_id in point_ids]
        favorable = [
            outcome
            for outcome in outcomes
            if len(neighbors[outcome[0]]) % 2 == 0
        ]
    elif event == "random_pair_has_common_neighbor":
        outcomes = list(itertools.combinations(point_ids, 2))
        favorable = [
            pair
            for pair in outcomes
            if neighbors[pair[0]] & neighbors[pair[1]]
        ]
    elif event == "random_edge_mixed_colors":
        outcomes = sorted(edges)
        favorable = [
            edge
            for edge in outcomes
            if private["colors"][edge[0]] != private["colors"][edge[1]]
        ]
    elif event == "random_triple_is_triangle":
        outcomes = list(itertools.combinations(point_ids, 3))
        favorable = [
            triple
            for triple in outcomes
            if all(
                tuple(sorted(pair)) in edges
                for pair in itertools.combinations(triple, 2)
            )
        ]
    else:
        raise AssertionError(f"Unexpected event: {event}")
    return len(favorable), len(outcomes), Fraction(len(favorable), len(outcomes))


def test_probability_uses_individual_graph_and_requires_exact_fraction() -> None:
    observed_events: set[str] = set()
    for difficulty in range(1, 6):
        for seed in range(35):
            public, private = generate_geometry_atlas_task(
                family=GEO_PROBABILITY_FAMILY,
                seed=seed,
                difficulty=difficulty,
            )
            favorable, total, exact = _independent_probability(private)
            observed_events.add(private["variant"])
            assert 0 < favorable < total
            assert private["favorable_outcomes"] == favorable
            assert private["total_outcomes"] == total
            assert public["content"]["sample_space_size"] == total
            assert private["probability"] == {
                "numerator": exact.numerator,
                "denominator": exact.denominator,
            }

            equivalent_fraction = (
                f"{exact.numerator * 2}/{exact.denominator * 2}"
            )
            correct = evaluate_geometry_atlas_answer(
                family=GEO_PROBABILITY_FAMILY,
                answer=f"/answer {equivalent_fraction}",
                private_state=private,
            )
            assert correct["parsed"] is True
            assert correct["correct"] is True
            wrong = evaluate_geometry_atlas_answer(
                family=GEO_PROBABILITY_FAMILY,
                answer="0/1",
                private_state=private,
            )
            assert wrong["parsed"] is True
            assert wrong["correct"] is False
            decimal = evaluate_geometry_atlas_answer(
                family=GEO_PROBABILITY_FAMILY,
                answer=str(float(exact)),
                private_state=private,
            )
            assert decimal["parsed"] is False

    assert observed_events == {
        "random_pair_is_edge",
        "random_vertex_even_degree",
        "random_pair_has_common_neighbor",
        "random_edge_mixed_colors",
        "random_triple_is_triangle",
    }


def test_invalid_family_difficulty_and_private_state_mismatch_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported Geometry Atlas family"):
        generate_geometry_atlas_task(
            family="unknown",
            seed=1,
            difficulty=1,
        )
    for family in SUPPORTED_FAMILIES:
        with pytest.raises(ValueError, match="difficulty must be at least 1"):
            generate_geometry_atlas_task(
                family=family,
                seed=1,
                difficulty=0,
            )

    _public, private = generate_geometry_atlas_task(
        family=GEO_TRANSFORM_FAMILY,
        seed=1,
        difficulty=1,
    )
    with pytest.raises(ValueError, match="does not match"):
        evaluate_geometry_atlas_answer(
            family=GEO_PROBABILITY_FAMILY,
            answer="1/2",
            private_state=private,
        )
