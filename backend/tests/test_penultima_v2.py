from __future__ import annotations

from copy import deepcopy

import pytest

from app.environments.chess_world.penultima import RULE_CATALOG
from app.environments.chess_world.penultima_v2 import (
    GENERATOR_VERSION,
    RULE_SPACE_VERSION,
    generate_penultima_task,
    legal_destinations,
    shortest_path,
    transition_penultima_move,
)


def _rule_identity(rule: dict) -> tuple[str, tuple[tuple[int, int], ...], int]:
    return (
        str(rule["movement"]),
        tuple(
            sorted(
                (int(vector[0]), int(vector[1]))
                for vector in rule["vectors"]
            )
        ),
        int(rule["max_distance"]),
    )


V1_RULE_IDENTITIES = {
    (
        rule.movement,
        tuple(sorted(rule.vectors)),
        rule.max_distance,
    )
    for rule in RULE_CATALOG
}


@pytest.mark.parametrize("difficulty", range(1, 6))
def test_generator_is_byte_for_byte_reproducible(difficulty: int):
    for seed in range(40):
        first = generate_penultima_task(
            seed=seed,
            difficulty=difficulty,
        )
        second = generate_penultima_task(
            seed=seed,
            difficulty=difficulty,
        )
        assert first == second


def test_generated_space_contains_a_rule_outside_v1_catalogue():
    # This seed is a stable fixture for micro-penultima-rules-v2.  Unlike the
    # old catalogue entries it combines three symmetric direction pairs.
    public, private = generate_penultima_task(seed=1, difficulty=3)
    rule = private["rule_spec"]

    assert private["rule_space_version"] == RULE_SPACE_VERSION
    assert GENERATOR_VERSION == "micro-penultima-rules-v2"
    assert "rule_key" not in private
    assert _rule_identity(rule) not in V1_RULE_IDENTITIES
    assert public["kind"] == "penultima_induction"


@pytest.mark.parametrize("seed", range(80))
def test_every_sampled_rule_has_at_least_four_symmetric_vectors(seed: int):
    _public, private = generate_penultima_task(
        seed=seed,
        difficulty=1 + seed % 5,
    )
    vectors = {
        (int(vector[0]), int(vector[1]))
        for vector in private["rule_spec"]["vectors"]
    }
    assert len(vectors) >= 4
    assert all((-delta_x, -delta_y) in vectors for delta_x, delta_y in vectors)


@pytest.mark.parametrize("difficulty", range(1, 6))
def test_shortest_solution_is_reachable_and_minimal(difficulty: int):
    for seed in range(32):
        _public, private = generate_penultima_task(
            seed=seed,
            difficulty=difficulty,
        )
        path = shortest_path(
            start=private["initial_square"],
            goal=private["goal_square"],
            rule_spec=private["rule_spec"],
            blockers=private["blockers"],
        )
        assert path is not None
        expected_moves = [
            f"{source}{target}"
            for source, target in zip(path, path[1:])
        ]
        assert expected_moves == private["shortest_solution"]
        assert len(expected_moves) == private["initial_shortest_path_length"]
        assert expected_moves
        assert len(
            legal_destinations(
                square=private["initial_square"],
                rule_spec=private["rule_spec"],
                blockers=private["blockers"],
            )
        ) >= 2


@pytest.mark.parametrize("seed", range(24))
def test_following_shortest_solution_completes_pure_transition(seed: int):
    public, private = generate_penultima_task(
        seed=seed,
        difficulty=1 + seed % 5,
    )
    original_public = deepcopy(public)
    original_private = deepcopy(private)
    state_public = public
    state_private = private
    solution = list(private["shortest_solution"])

    for index, move in enumerate(solution, start=1):
        transitioned = transition_penultima_move(
            move=move,
            public_state=state_public,
            private_state=state_private,
        )
        assert transitioned.accepted is True
        assert transitioned.completed is (index == len(solution))
        state_public = transitioned.public_state
        state_private = transitioned.private_state

    assert public == original_public
    assert private == original_private
    assert state_private["current_square"] == private["goal_square"]
    assert state_public["current_square"] == public["goal_square"]
    assert transitioned.reason == "goal_reached"
    assert transitioned.evaluation_state is not None
    assert transitioned.evaluation_state["correct"] is True
    assert transitioned.evaluation_state["continuous_score"] == 1.0


def test_broad_seed_series_does_not_fail_and_remains_non_degenerate():
    fingerprints: set[str] = set()
    positions: set[tuple[str, str]] = set()
    for seed in range(1000):
        public, private = generate_penultima_task(
            seed=seed,
            difficulty=1 + seed % 5,
        )
        assert public["current_square"] != public["goal_square"]
        assert private["shortest_solution"]
        fingerprints.add(private["rule_fingerprint"])
        positions.add(
            (private["initial_square"], private["goal_square"])
        )

    assert len(fingerprints) >= 20
    assert len(positions) >= 200
