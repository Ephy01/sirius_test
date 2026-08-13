from __future__ import annotations

from app.environments.chess_world.chess_coverage import (
    evaluate_chess_coverage_answer,
    generate_chess_coverage_task,
    generate_legacy_chess_coverage_task,
    transition_chess_coverage_action,
)
from app.environments.machines.machine_reach import (
    LAMPS_GF2,
    generate_machine_reach_task,
    transition_machine_action,
)


def test_generator_is_deterministic_and_has_an_exact_cost_optimum():
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
            assert public["variant"] == "custom_jump_placement"
            assert public["board_size"] == 8
            assert len(public["piece_types"]) == 4
            assert 2 <= len(private["optimal_placements"]) <= public["max_placements"]
            assert private["optimal_cost"] > 0


def test_placement_is_logged_resettable_and_exactly_scored():
    public, private = generate_chess_coverage_task(seed=41, difficulty=4)
    solution = private["optimal_placements"]
    current_public, current_private = public, private
    for index, placement in enumerate(solution):
        transition = transition_chess_coverage_action(
            action_type="apply_op",
            op_id=(
                f"place:{placement['piece']}:"
                f"{placement['row']}:{placement['col']}"
            ),
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
    assert result["selected_cost"] == result["optimal_cost"]

    reset = transition_chess_coverage_action(
        action_type="reset",
        client_action_id="reset-1",
        public_state=current_public,
        private_state=current_private,
    )
    assert reset.accepted is True
    assert reset.public_state["placements"] == []
    assert reset.public_state["total_cost"] == 0
    assert reset.private_state["interaction"]["reset_count"] == 1


def test_repeated_piece_cost_increases_and_piece_can_be_removed():
    public, private = generate_chess_coverage_task(seed=8, difficulty=2)
    targets = {tuple(point) for point in private["targets"]}
    squares = [
        (row, col)
        for row in range(8)
        for col in range(8)
        if (row, col) not in targets
    ][:2]
    first = transition_chess_coverage_action(
        action_type="apply_op",
        op_id=f"place:Q:{squares[0][0]}:{squares[0][1]}",
        client_action_id="queen-1",
        public_state=public,
        private_state=private,
    )
    second = transition_chess_coverage_action(
        action_type="apply_op",
        op_id=f"place:Q:{squares[1][0]}:{squares[1][1]}",
        client_action_id="queen-2",
        public_state=first.public_state,
        private_state=first.private_state,
    )
    assert [item["cost"] for item in second.public_state["placements"]] == [6, 11]
    assert second.public_state["total_cost"] == 17

    removed = transition_chess_coverage_action(
        action_type="apply_op",
        op_id="remove:P1",
        client_action_id="remove-queen-1",
        public_state=second.public_state,
        private_state=second.private_state,
    )
    assert removed.accepted is True
    assert removed.public_state["total_cost"] == 6


def test_legacy_task_remains_interactive_and_scorable():
    public, private = generate_legacy_chess_coverage_task(seed=41, difficulty=4)
    current_public, current_private = public, private
    for index, candidate_id in enumerate(private["optimal_solutions"][0]):
        transition = transition_chess_coverage_action(
            action_type="apply_op",
            op_id=candidate_id,
            client_action_id=f"legacy-{index}",
            public_state=current_public,
            private_state=current_private,
        )
        current_public, current_private = (
            transition.public_state,
            transition.private_state,
        )
    result = evaluate_chess_coverage_answer(
        answer="done",
        private_state=current_private,
    )
    assert result["correct"] is True


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
