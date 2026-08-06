from __future__ import annotations

import time

from app.environments.core.rule_dsl import (
    compile_truth_masks,
    enumerate_rules,
)
from app.environments.core.rule_space import (
    clear_rule_space_cache,
    get_rule_space,
)
from app.environments.geometry_world.atlas import (
    evaluate_geo_zendo_answer,
    generate_geo_zendo_task,
)
from app.environments.geometry_world.zendo_v2 import (
    PROBE_BUDGET,
    evaluate_geo_zendo_v2_answer,
    generate_geo_zendo_v2_task,
    transition_geo_zendo_v2_probe,
)
from app.environments.geometry_world import GENERATOR_VERSION as LEGACY_GENERATOR_VERSION
from app.environments.registry import interact_task


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key for item in value.values() for key in nested_keys(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in nested_keys(item)}
    return set()


def test_rule_space_is_cached_balanced_and_cheapest_by_truth():
    clear_rule_space_cache()
    started = time.perf_counter()
    space = get_rule_space()
    cold_seconds = time.perf_counter() - started
    assert cold_seconds < 3
    assert get_rule_space() is space
    assert len(space.universe) == 1200
    assert all(space.indices_for_difficulty(level) for level in range(1, 6))
    assert all(0.12 <= space.base_rate(index) <= 0.88 for index in range(len(space.rules)))

    raw_rules = enumerate_rules()
    raw_masks = compile_truth_masks(raw_rules, space.universe)
    cheapest: dict[int, int] = {}
    for rule, truth_mask in zip(raw_rules, raw_masks, strict=True):
        base_rate = truth_mask.bit_count() / len(space.universe)
        if 0.12 <= base_rate <= 0.88:
            cheapest[truth_mask] = min(
                cheapest.get(truth_mask, rule.mdl),
                rule.mdl,
            )
    distilled_masks = compile_truth_masks(space.rules, space.universe)
    assert all(
        rule.mdl == cheapest[truth_mask]
        for rule, truth_mask in zip(
            space.rules,
            distilled_masks,
            strict=True,
        )
    )


def test_zendo_v2_is_reproducible_balanced_and_does_not_leak():
    for difficulty in range(1, 6):
        for seed in range(12):
            first = generate_geo_zendo_v2_task(
                seed=seed,
                difficulty=difficulty,
            )
            second = generate_geo_zendo_v2_task(
                seed=seed,
                difficulty=difficulty,
            )
            assert first == second
            public, private = first
            assert len(public["content"]["examples"]) == 4
            assert len(public["content"]["probe_cards"]) == 12
            assert len(public["content"]["targets"]) == 8
            assert len(private["target_answers"]) == 8
            assert sum(private["target_answers"]) == 4
            assert 8 <= int(private["version_space_after_examples"]).bit_count() <= 64
            assert nested_keys(public).isdisjoint(
                {
                    "rule_index",
                    "rule_key",
                    "rule_text",
                    "version_space",
                    "target_answers",
                    "truth_mask",
                    "probe_truth_masks",
                    "private_state",
                }
            )


def test_zendo_probe_budget_telemetry_and_score():
    public, private = generate_geo_zendo_v2_task(seed=2026, difficulty=4)
    for index in range(PROBE_BUDGET):
        card_id = public["content"]["probe_cards"][index]["card_id"]
        transitioned = transition_geo_zendo_v2_probe(
            card_id=card_id,
            public_state=public,
            private_state=private,
        )
        assert transitioned.accepted is True
        assert transitioned.telemetry is not None
        telemetry = transitioned.telemetry
        assert telemetry["vs_size_before"] >= telemetry["vs_size_after"] >= 1
        assert telemetry["gain_bits_actual"] >= 0
        assert telemetry["gain_bits_best"] >= 0
        public, private = (
            transitioned.public_state,
            transitioned.private_state,
        )
    assert private["probes_remaining"] == 0

    sixth_card = public["content"]["probe_cards"][PROBE_BUDGET]["card_id"]
    exhausted = transition_geo_zendo_v2_probe(
        card_id=sixth_card,
        public_state=public,
        private_state=private,
    )
    assert exhausted.accepted is False
    assert exhausted.reason == "probe_budget_exhausted"

    answer = " ".join(
        "да" if value else "нет"
        for value in private["target_answers"]
    )
    evaluation = evaluate_geo_zendo_v2_answer(
        answer=answer,
        private_state=private,
    )
    assert evaluation["correct"] is True
    assert evaluation["accuracy"] == 1
    assert evaluation["continuous_score"] == 1
    assert evaluation["zendo_score"] == 1


def test_zendo_warm_generation_smoke_and_legacy_evaluator():
    generate_geo_zendo_v2_task(seed=99, difficulty=3)
    started = time.perf_counter()
    for seed in range(100):
        generate_geo_zendo_v2_task(
            seed=seed + 1_000,
            difficulty=seed % 5 + 1,
        )
    assert time.perf_counter() - started < 5

    legacy_public, legacy_private = generate_geo_zendo_task(
        seed=17,
        difficulty=3,
    )
    assert legacy_public["variant"] == "classify_hidden_geometric_rule"
    legacy_answer = " ".join(
        "да" if value else "нет"
        for value in legacy_private["target_answers"]
    )
    assert evaluate_geo_zendo_answer(
        answer=legacy_answer,
        private_state=legacy_private,
    )["correct"] is True


def test_legacy_zendo_isolated_point_hint_is_supported():
    public, private = generate_geo_zendo_task(seed=0, difficulty=2)
    assert private["rule_key"] == "has_isolated_point"

    transition = interact_task(
        family="geo_zendo",
        generator_version=LEGACY_GENERATOR_VERSION,
        action_type="hint",
        action_payload={},
        public_state=public,
        private_state=private,
    )

    assert transition.accepted is True
    assert "Подсказка" in transition.message
