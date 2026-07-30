from __future__ import annotations

from copy import deepcopy

import pytest

from app.environments.machines.machine_reach import (
    CHESS_KIND,
    FAMILY_KEY,
    GENERATOR_VERSION,
    LAMPS_GF2,
    LEAPER_BOARD,
    MACHINE_PANEL_KIND,
    NUMERIC_MACHINE,
    PERM_PUZZLE,
    SUB_KINDS,
    evaluate_machine_answer,
    generate_machine_reach_task,
    shortest_witness,
    simulate_witness,
    telemetry_aggregates,
    transition_machine_action,
    validate_machine_instance,
    validate_unreachable_certificate,
)

FORBIDDEN_PUBLIC_KEYS = {
    "reachable",
    "witness",
    "min_len",
    "certificate",
    "history",
    "interaction",
    "processed_actions",
}


def _nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for nested in value.values()
            for key in _nested_keys(nested)
        }
    if isinstance(value, list):
        return {
            key
            for nested in value
            for key in _nested_keys(nested)
        }
    return set()


def _first_seed(sub_kind: str, *, reachable: bool) -> int:
    for seed in range(8):
        public, private = generate_machine_reach_task(
            seed=seed,
            difficulty=3,
            sub_kind=sub_kind,
        )
        assert public["sub_kind"] == sub_kind
        if private["reachable"] is reachable:
            return seed
    raise AssertionError("Reachability split must contain both classes")


@pytest.mark.parametrize("sub_kind", SUB_KINDS)
def test_generators_are_deterministic_private_and_solver_checked(sub_kind: str):
    for difficulty in range(1, 6):
        for seed in range(24):
            public, private = generate_machine_reach_task(
                seed=seed,
                difficulty=difficulty,
                sub_kind=sub_kind,
            )
            repeated = generate_machine_reach_task(
                seed=seed,
                difficulty=difficulty,
                sub_kind=sub_kind,
            )
            assert (public, private) == repeated
            assert public["sub_kind"] == sub_kind
            assert public["kind"] == (
                CHESS_KIND if sub_kind == LEAPER_BOARD else MACHINE_PANEL_KIND
            )
            assert public["start"] != public["target"]
            assert public["current"] == public["start"]
            assert public["steps_soft_cap"] == 24
            assert private["family"] == FAMILY_KEY
            assert private["generator_version"] == GENERATOR_VERSION
            assert private["difficulty"] == difficulty
            assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
            assert validate_machine_instance(
                public_state=public,
                private_state=private,
            )

            if private["reachable"]:
                witness = shortest_witness(public_state=public)
                assert witness is not None
                assert len(witness) == private["min_len"]
                assert witness
                assert simulate_witness(
                    public_state=public,
                    private_state=private,
                ) == private["target"]
                assert private["certificate"] is None
            else:
                assert shortest_witness(public_state=public) is None
                assert validate_unreachable_certificate(
                    public_state=public,
                    private_state=private,
                )


@pytest.mark.parametrize("sub_kind", SUB_KINDS)
def test_one_thousand_seeds_have_balanced_reachability(sub_kind: str):
    reachable_count = 0
    certificate_kinds: set[str] = set()
    for seed in range(1000):
        public, private = generate_machine_reach_task(
            seed=seed,
            difficulty=1 + seed % 5,
            sub_kind=sub_kind,
        )
        reachable_count += int(private["reachable"])
        if not private["reachable"]:
            certificate_kinds.add(private["certificate"]["kind"])
            assert validate_unreachable_certificate(
                public_state=public,
                private_state=private,
            )
        assert validate_machine_instance(
            public_state=public,
            private_state=private,
        )
    assert 450 <= reachable_count <= 550
    assert certificate_kinds


@pytest.mark.parametrize("sub_kind", SUB_KINDS)
def test_apply_undo_contract_is_pure_idempotent_and_explicit(sub_kind: str):
    seed = _first_seed(sub_kind, reachable=True)
    public, private = generate_machine_reach_task(
        seed=seed,
        difficulty=3,
        sub_kind=sub_kind,
    )
    original_public = deepcopy(public)
    original_private = deepcopy(private)
    first_op = private["witness"][0]

    applied = transition_machine_action(
        action_type="apply_op",
        op_id=first_op,
        client_action_id="action-1",
        first_action_latency_ms=735,
        public_state=public,
        private_state=private,
    )
    assert applied.accepted is True
    assert applied.completed is False
    assert applied.private_state["current"] != private["current"]
    assert applied.private_state["interaction"]["first_action_latency_ms"] == 735
    assert public == original_public
    assert private == original_private

    repeated = transition_machine_action(
        action_type="apply_op",
        op_id=first_op,
        client_action_id="action-1",
        first_action_latency_ms=999,
        public_state=applied.public_state,
        private_state=applied.private_state,
    )
    assert repeated.public_state == applied.public_state
    assert repeated.private_state == applied.private_state
    assert repeated.accepted == applied.accepted

    with pytest.raises(ValueError, match="reused"):
        transition_machine_action(
            action_type="undo",
            client_action_id="action-1",
            public_state=applied.public_state,
            private_state=applied.private_state,
        )

    undone = transition_machine_action(
        action_type="undo",
        client_action_id="undo-1",
        public_state=applied.public_state,
        private_state=applied.private_state,
    )
    assert undone.accepted is True
    assert undone.private_state["current"] == private["start"]
    assert undone.private_state["interaction"]["undo_count"] == 1

    repeated_undo = transition_machine_action(
        action_type="undo",
        client_action_id="undo-1",
        public_state=undone.public_state,
        private_state=undone.private_state,
    )
    assert repeated_undo.private_state == undone.private_state


@pytest.mark.parametrize("sub_kind", SUB_KINDS)
def test_witness_then_done_produces_continuous_score_and_aggregates(sub_kind: str):
    seed = _first_seed(sub_kind, reachable=True)
    public, private = generate_machine_reach_task(
        seed=seed,
        difficulty=3,
        sub_kind=sub_kind,
    )
    state_public = public
    state_private = private
    for index, op_id in enumerate(private["witness"], start=1):
        transitioned = transition_machine_action(
            action_type="apply_op",
            op_id=op_id,
            client_action_id=f"solve-{index}",
            first_action_latency_ms=420 if index == 1 else None,
            public_state=state_public,
            private_state=state_private,
        )
        state_public = transitioned.public_state
        state_private = transitioned.private_state

    assert state_private["current"] == state_private["target"]
    evaluation = evaluate_machine_answer(
        answer="done",
        private_state=state_private,
    )
    assert evaluation["accepted"] is True
    assert evaluation["correct"] is True
    assert evaluation["should_finalize"] is True
    assert evaluation["continuous_score"] == 1.0
    assert evaluation["first_action_latency_ms"] == 420
    assert evaluation["len_ratio"] == 1.0
    assert evaluation["false_impossible"] is False


def test_false_impossible_freezes_but_does_not_finalize():
    seed = _first_seed(NUMERIC_MACHINE, reachable=True)
    _public, private = generate_machine_reach_task(
        seed=seed,
        difficulty=4,
        sub_kind=NUMERIC_MACHINE,
    )
    evaluation = evaluate_machine_answer(
        answer="impossible",
        private_state=private,
    )
    assert evaluation["accepted"] is False
    assert evaluation["correct"] is False
    assert evaluation["should_finalize"] is False
    assert evaluation["continuous_score"] == 0
    assert evaluation["freeze_seconds"] == 15
    assert evaluation["false_impossible"] is True


def test_correct_impossible_is_terminal_and_done_before_target_is_neutral():
    unreachable_seed = _first_seed(LAMPS_GF2, reachable=False)
    _public, unreachable = generate_machine_reach_task(
        seed=unreachable_seed,
        difficulty=2,
        sub_kind=LAMPS_GF2,
    )
    impossible = evaluate_machine_answer(
        answer="недостижимо",
        private_state=unreachable,
    )
    assert impossible["correct"] is True
    assert impossible["should_finalize"] is True
    assert impossible["continuous_score"] == 1

    reachable_seed = _first_seed(PERM_PUZZLE, reachable=True)
    _public, reachable = generate_machine_reach_task(
        seed=reachable_seed,
        difficulty=3,
        sub_kind=PERM_PUZZLE,
    )
    early_done = evaluate_machine_answer(
        answer="done",
        private_state=reachable,
    )
    assert early_done["accepted"] is False
    assert early_done["should_finalize"] is False
    assert early_done["evidence"] == 0


def test_revisited_state_ratio_and_invalid_operation_are_counted_safely():
    seed = _first_seed(LAMPS_GF2, reachable=True)
    public, private = generate_machine_reach_task(
        seed=seed,
        difficulty=2,
        sub_kind=LAMPS_GF2,
    )
    rejected = transition_machine_action(
        action_type="apply_op",
        op_id="does-not-exist",
        client_action_id="bad-op",
        public_state=public,
        private_state=private,
    )
    assert rejected.accepted is False
    assert rejected.private_state["interaction"]["apply_count"] == 0

    op_id = public["ops"][0]["id"]
    first = transition_machine_action(
        action_type="apply_op",
        op_id=op_id,
        client_action_id="toggle-1",
        public_state=rejected.public_state,
        private_state=rejected.private_state,
    )
    second = transition_machine_action(
        action_type="apply_op",
        op_id=op_id,
        client_action_id="toggle-2",
        public_state=first.public_state,
        private_state=first.private_state,
    )
    assert second.private_state["current"] == private["start"]
    aggregates = telemetry_aggregates(second.private_state)
    assert aggregates["actual_length"] == 2
    assert aggregates["revisited_states"] == 0.5
