from __future__ import annotations

from collections import Counter

import pytest

from app.environments.nim_like import (
    FAMILY_KEY,
    GENERATOR_VERSION,
    MISERE_MODE,
    MODES,
    NORMAL_MODE,
    NimMove,
    apply_nim_move,
    evaluate_nim_like_answer,
    generate_nim_like_task,
    grundy_value,
    legal_moves,
    parse_nim_answer,
    position_grundy,
    solve_nim_position,
    validate_nim_like_instance,
)

FORBIDDEN_PUBLIC_KEYS = {
    "winning",
    "legal_moves",
    "winning_moves",
    "grundy_values",
    "nim_sum",
    "private_state",
}
MANDATORY_EVALUATION_KEYS = {
    "family",
    "generator_version",
    "difficulty",
    "continuous_score",
    "score",
    "regret",
    "best_resulting_grundy",
    "mode",
    "position_winning",
    "answer_kind",
    "legal",
    "correct",
    "resulting_grundy",
    "resulting_position_winning",
    "false_losing_claim",
    "freeze_seconds",
    "evidence",
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


def _task_with(
    *,
    mode: str,
    winning: bool,
) -> tuple[dict, dict]:
    for seed in range(12):
        public, private = generate_nim_like_task(
            seed=seed,
            difficulty=4,
            mode=mode,
        )
        if private["winning"] is winning:
            return public, private
    raise AssertionError("The deterministic 60/40 split must contain both classes")


def _move_text(move: dict[str, int]) -> str:
    return f"take {move['heap']} {move['count']}"


def test_known_grundy_values_and_normal_play_outcomes():
    assert [grundy_value(size, (1, 2)) for size in range(7)] == [
        0,
        1,
        2,
        0,
        1,
        2,
        0,
    ]
    values, nim_sum = position_grundy((1, 2), ((1,), (1,)))
    assert values == (1, 0)
    assert nim_sum == 1

    winning = solve_nim_position(
        heaps=(1,),
        rule_sets=((1,),),
        mode=NORMAL_MODE,
    )
    assert winning.winning is True
    assert winning.winning_moves == (NimMove(heap=1, count=1),)

    losing = solve_nim_position(
        heaps=(1, 1),
        rule_sets=((1,), (1,)),
        mode=NORMAL_MODE,
    )
    assert losing.winning is False
    assert losing.winning_moves == ()


def test_misere_solver_uses_exact_terminal_convention_not_normal_nim_sum():
    one_counter = solve_nim_position(
        heaps=(1,),
        rule_sets=((1,),),
        mode=MISERE_MODE,
    )
    assert one_counter.nim_sum == 1
    assert one_counter.winning is False
    assert one_counter.winning_moves == ()

    two_singletons = solve_nim_position(
        heaps=(1, 1),
        rule_sets=((1,), (1,)),
        mode=MISERE_MODE,
    )
    assert two_singletons.nim_sum == 0
    assert two_singletons.winning is True
    assert set(two_singletons.winning_moves) == {
        NimMove(heap=1, count=1),
        NimMove(heap=2, count=1),
    }


@pytest.mark.parametrize("mode", MODES)
def test_generator_is_deterministic_private_and_exact(mode: str):
    observed_rule_kinds: Counter[str] = Counter()
    for difficulty in range(1, 6):
        for seed in range(40):
            public, private = generate_nim_like_task(
                seed=seed,
                difficulty=difficulty,
                mode=mode,
            )
            assert (public, private) == generate_nim_like_task(
                seed=seed,
                difficulty=difficulty,
                mode=mode,
            )
            assert public["kind"] == "counters"
            assert public["mode"] == mode
            assert 1 <= len(public["heaps"]) <= 4
            assert len(private["legal_moves"]) >= 2
            assert private["family"] == FAMILY_KEY
            assert private["generator_version"] == GENERATOR_VERSION
            assert private["winning"] == bool(private["winning_moves"])
            assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
            assert validate_nim_like_instance(
                public_state=public,
                private_state=private,
            )
            observed_rule_kinds[public["rules"]["kind"]] += 1
    assert observed_rule_kinds["global"] > 0
    assert observed_rule_kinds["per_heap"] > 0


@pytest.mark.parametrize("mode", MODES)
def test_one_thousand_seeds_are_sixty_forty_and_self_check(mode: str):
    winning_count = 0
    for seed in range(1000):
        public, private = generate_nim_like_task(
            seed=seed,
            difficulty=1 + seed % 5,
            mode=mode,
        )
        winning_count += int(private["winning"])
        assert validate_nim_like_instance(
            public_state=public,
            private_state=private,
        )
    assert 550 <= winning_count <= 650
    assert winning_count == 600


def test_default_mode_selection_is_deterministic_and_covers_both_modes():
    observed = {
        generate_nim_like_task(seed=seed, difficulty=2)[0]["mode"]
        for seed in range(20)
    }
    assert observed == {NORMAL_MODE, MISERE_MODE}


def test_move_application_legality_and_answer_parser():
    rules = ((1, 3), (2,))
    assert legal_moves((2, 2), rules) == (
        NimMove(heap=1, count=1),
        NimMove(heap=2, count=2),
    )
    assert apply_nim_move((2, 2), NimMove(1, 1), rules) == (1, 2)
    assert apply_nim_move((2, 2), NimMove(1, 3), rules) is None
    assert apply_nim_move((2, 2), NimMove(3, 1), rules) is None

    assert parse_nim_answer("take 2 3").move == NimMove(2, 3)
    assert parse_nim_answer("ВЗЯТЬ 1 2").normalized == "take 1 2"
    assert parse_nim_answer("  проигрышная позиция ").kind == "losing"
    assert parse_nim_answer("move 1 2").kind == "invalid"


@pytest.mark.parametrize("mode", MODES)
def test_winning_move_has_zero_regret_and_all_telemetry(mode: str):
    _public, private = _task_with(mode=mode, winning=True)
    move = private["winning_moves"][0]
    evaluation = evaluate_nim_like_answer(
        answer=_move_text(move),
        private_state=private,
    )
    assert MANDATORY_EVALUATION_KEYS <= set(evaluation)
    assert evaluation["legal"] is True
    assert evaluation["correct"] is True
    assert evaluation["continuous_score"] == 1
    assert evaluation["score"] == 1
    assert evaluation["regret"] == 0
    assert evaluation["resulting_position_winning"] is False
    if mode == NORMAL_MODE:
        assert evaluation["resulting_grundy"] == 0


@pytest.mark.parametrize("mode", MODES)
def test_losing_declaration_and_false_claim_economy(mode: str):
    _public, losing = _task_with(mode=mode, winning=False)
    correct = evaluate_nim_like_answer(
        answer="проигрышная",
        private_state=losing,
    )
    assert MANDATORY_EVALUATION_KEYS <= set(correct)
    assert correct["correct"] is True
    assert correct["continuous_score"] == 1
    assert correct["regret"] == 0
    assert correct["freeze_seconds"] == 0

    _public, winning = _task_with(mode=mode, winning=True)
    false_claim = evaluate_nim_like_answer(
        answer="losing",
        private_state=winning,
    )
    assert MANDATORY_EVALUATION_KEYS <= set(false_claim)
    assert false_claim["correct"] is False
    assert false_claim["continuous_score"] == 0
    assert false_claim["regret"] == 1
    assert false_claim["false_losing_claim"] is True
    assert false_claim["freeze_seconds"] == 15


@pytest.mark.parametrize("mode", MODES)
def test_non_winning_and_illegal_moves_have_regret(mode: str):
    _public, private = _task_with(mode=mode, winning=True)
    winning_moves = {
        (move["heap"], move["count"])
        for move in private["winning_moves"]
    }
    non_winning = next(
        (
            move
            for move in private["legal_moves"]
            if (move["heap"], move["count"]) not in winning_moves
        ),
        None,
    )
    if non_winning is not None:
        evaluated = evaluate_nim_like_answer(
            answer=_move_text(non_winning),
            private_state=private,
        )
        assert evaluated["legal"] is True
        assert evaluated["correct"] is False
        assert evaluated["regret"] >= 0
        assert evaluated["continuous_score"] == 0
        assert evaluated["freeze_seconds"] == 0

    illegal = evaluate_nim_like_answer(
        answer="take 99 99",
        private_state=private,
    )
    assert MANDATORY_EVALUATION_KEYS <= set(illegal)
    assert illegal["legal"] is False
    assert illegal["regret"] == 1
    assert illegal["continuous_score"] == 0


def test_regret_is_exact_grundy_gap_not_a_binary_error_flag():
    private = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": 2,
        "mode": NORMAL_MODE,
        "heaps": [3],
        "rule_sets": [[1, 2, 3]],
        "winning": True,
    }
    evaluated = evaluate_nim_like_answer(
        answer="take 1 1",
        private_state=private,
    )
    assert evaluated["correct"] is False
    assert evaluated["resulting_grundy"] == 2
    assert evaluated["best_resulting_grundy"] == 0
    assert evaluated["regret"] == 2
