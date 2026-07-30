from itertools import combinations

from app.environments.chess_world.chess960 import (
    GENERATOR_VERSION,
    LEGACY_GENERATOR_VERSION,
    enumerate_chess960_repairs,
    evaluate_chess960_answer,
    evaluate_chess960_validation_answer,
    generate_chess960_task,
    generate_chess960_validation_task,
    is_valid_chess960,
    parse_chess960_repair_answer,
    swap_back_rank_files,
)


FILES = "abcdefgh"
EXPECTED_PUBLIC_KEYS = {
    "kind",
    "variant",
    "prompt",
    "back_rank",
    "response_hint",
}


def _apply_repair(back_rank: str, repair: tuple[str, str]) -> str:
    first_file = FILES.index(repair[0][0])
    second_file = FILES.index(repair[1][0])
    return swap_back_rank_files(back_rank, first_file, second_file)


def test_versions_and_legacy_validation_remain_callable():
    assert GENERATOR_VERSION == "chess960-mission-v2"
    assert LEGACY_GENERATOR_VERSION == "chess960-validation-v1"

    first = generate_chess960_validation_task(seed=41, difficulty=1)
    repeated = generate_chess960_validation_task(seed=41, difficulty=1)
    assert first == repeated
    public_state, private_state = first
    assert public_state["kind"] == "chess960_validation"
    assert "response_hint" in public_state
    assert "variant" not in private_state

    expected_answer = "да" if private_state["is_valid"] else "нет"
    evaluation = evaluate_chess960_validation_answer(
        answer=expected_answer,
        private_state=private_state,
    )
    assert evaluation["correct"] is True


def test_current_generator_is_deterministic_and_repairs_are_exhaustive():
    expected_variants = {
        1: "single_swap_repair",
        2: "single_swap_repair",
        3: "single_swap_repair",
        4: "single_swap_repair",
        5: "repair_count",
        8: "repair_count",
    }

    observed_ranks: set[str] = set()
    for difficulty, expected_variant in expected_variants.items():
        for seed in range(100):
            first = generate_chess960_task(
                seed=seed,
                difficulty=difficulty,
            )
            repeated = generate_chess960_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert first == repeated

            public_state, private_state = first
            assert set(public_state) == EXPECTED_PUBLIC_KEYS
            assert public_state["kind"] == "chess960_mission"
            assert public_state["variant"] == expected_variant
            assert private_state["variant"] == expected_variant
            assert len(public_state["back_rank"]) == 8
            observed_ranks.add(public_state["back_rank"])

            back_rank = public_state["back_rank"]
            assert is_valid_chess960(back_rank) is False
            enumerated = enumerate_chess960_repairs(back_rank)
            stored = tuple(
                tuple(pair)
                for pair in private_state["valid_repairs"]
            )
            assert stored == enumerated
            assert private_state["repair_count"] == len(enumerated)
            assert private_state["repair_count"] >= 1
            assert all(
                is_valid_chess960(_apply_repair(back_rank, repair))
                for repair in enumerated
            )

            all_valid_pairs = {
                (f"{FILES[first]}1", f"{FILES[second]}1")
                for first, second in combinations(range(8), 2)
                if is_valid_chess960(
                    swap_back_rank_files(back_rank, first, second)
                )
            }
            assert set(enumerated) == all_valid_pairs

    assert len(observed_ranks) >= 100


def test_single_swap_accepts_every_valid_pair_and_required_formats():
    public_state, private_state = generate_chess960_task(
        seed=808,
        difficulty=3,
    )
    assert public_state["variant"] == "single_swap_repair"
    valid_repairs = [
        tuple(pair)
        for pair in private_state["valid_repairs"]
    ]

    for first, second in valid_repairs:
        answers = (
            f"{first} {second}",
            f"{first[0]} {second[0]}",
            f"{first}-{second}",
            f"{second} {first}",
        )
        for answer in answers:
            evaluation = evaluate_chess960_answer(
                answer=answer,
                private_state=private_state,
            )
            assert evaluation["parsed"] is True
            assert evaluation["correct"] is True

    assert parse_chess960_repair_answer("a1 b1") == ("a1", "b1")
    assert parse_chess960_repair_answer("a b") == ("a1", "b1")
    assert parse_chess960_repair_answer("b1-a1") == ("a1", "b1")
    assert parse_chess960_repair_answer("a1 a1") is None
    assert parse_chess960_repair_answer("a1 i1") is None

    valid_set = set(valid_repairs)
    wrong_pair = next(
        (f"{FILES[first]}1", f"{FILES[second]}1")
        for first, second in combinations(range(8), 2)
        if (f"{FILES[first]}1", f"{FILES[second]}1") not in valid_set
    )
    wrong = evaluate_chess960_answer(
        answer=f"{wrong_pair[0]} {wrong_pair[1]}",
        private_state=private_state,
    )
    assert wrong["parsed"] is True
    assert wrong["correct"] is False

    malformed = evaluate_chess960_answer(
        answer="переставить слона",
        private_state=private_state,
    )
    assert malformed["parsed"] is False
    assert malformed["correct"] is False


def test_repair_count_evaluation_and_saved_v2_validation_evaluation():
    count_public, count_private = generate_chess960_task(
        seed=909,
        difficulty=6,
    )
    assert count_public["variant"] == "repair_count"
    repair_count = count_private["repair_count"]

    correct = evaluate_chess960_answer(
        answer=str(repair_count),
        private_state=count_private,
    )
    assert correct == {
        "correct": True,
        "parsed": True,
        "submitted_count": repair_count,
    }
    incorrect = evaluate_chess960_answer(
        answer=str(repair_count + 1),
        private_state=count_private,
    )
    assert incorrect["parsed"] is True
    assert incorrect["correct"] is False
    malformed = evaluate_chess960_answer(
        answer="две пары",
        private_state=count_private,
    )
    assert malformed["parsed"] is False
    assert malformed["correct"] is False

    legacy_public, legacy_private = generate_chess960_validation_task(
        seed=101,
        difficulty=1,
    )
    saved_v2_private = {
        **legacy_private,
        "variant": "validation",
        "valid_repairs": [],
        "repair_count": 0,
    }
    expected = "да" if saved_v2_private["is_valid"] else "нет"
    validation = evaluate_chess960_answer(
        answer=expected,
        private_state=saved_v2_private,
    )
    assert validation["correct"] is True

    # The public part of a previously stored mission is not regenerated, but
    # it used the same legacy validation payload wrapped as a v2 mission.
    assert legacy_public["kind"] == "chess960_validation"
