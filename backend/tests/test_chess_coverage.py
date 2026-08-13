from __future__ import annotations

from app.environments.chess_world.chess_coverage import (
    evaluate_chess_coverage_answer,
    generate_chess_coverage_task,
    transition_chess_coverage_action,
)
from app.environments.machines.machine_reach import (
    LAMPS_GF2,
    generate_machine_reach_task,
    transition_machine_action,
)


def test_generator_is_deterministic_and_has_a_unique_weighted_optimum():
    for difficulty in range(1, 6):
        for seed in range(12):
            first = generate_chess_coverage_task(
                seed=seed,
                difficulty=difficulty,
            )
            second = generate_chess_coverage_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert first == second
            public, private = first
            assert public["kind"] == "chess_coverage"
            assert len(private["optimal_solutions"]) == 1
            assert 2 <= len(private["optimal_solutions"][0]) <= 4
            assert private["optimal_weight"] > 0


def test_selection_is_logged_resettable_and_exactly_scored():
    public, private = generate_chess_coverage_task(seed=41, difficulty=4)
    solution = private["optimal_solutions"][0]
    current_public, current_private = public, private
    for index, candidate_id in enumerate(solution):
        transition = transition_chess_coverage_action(
            action_type="apply_op",
            op_id=candidate_id,
            client_action_id=f"place-{index}",
            public_state=current_public,
            private_state=current_private,
        )
        assert transition.accepted is True
        current_public = transition.public_state
        current_private = transition.private_state

    assert current_public["all_covered"] is True
    result = evaluate_chess_coverage_answer(
        answer="done",
        private_state=current_private,
    )
    assert result["correct"] is True
    assert result["selected_weight"] == result["optimal_weight"]

    reset = transition_chess_coverage_action(
        action_type="reset",
        client_action_id="reset-1",
        public_state=current_public,
        private_state=current_private,
    )
    assert reset.accepted is True
    assert reset.public_state["selected_ids"] == []
    assert reset.public_state["total_weight"] == 0
    assert reset.private_state["interaction"]["reset_count"] == 1

def test_lamp_machine_reset_restores_start_and_keeps_telemetry_count():
    public, private = generate_machine_reach_task(
        seed=17,
        difficulty=2,
        sub_kind=LAMPS_GF2,
    )
    changed = transition_machine_action(
        action_type="apply_op",
        op_id=public["ops"][0]["id"],
        client_action_id="lamp-op",
        public_state=public,
        private_state=private,
    )
    reset = transition_machine_action(
        action_type="reset",
        client_action_id="lamp-reset",
        public_state=changed.public_state,
        private_state=changed.private_state,
    )
    assert reset.accepted is True
    assert reset.private_state["current"] == reset.private_state["start"]
    assert reset.private_state["history"] == []
    assert reset.private_state["interaction"]["reset_count"] == 1
