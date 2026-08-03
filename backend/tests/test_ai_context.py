"""Unit battery for the safe AI context builders (ТЗ Alice AI §22.1)."""

from __future__ import annotations

import json

from app.ai import build_task_context
from app.environments import generate_task, generator_version_for
from app.environments.geometry_world.zendo_v2 import transition_geo_zendo_v2_probe
from app.models import TaskInstance

FORBIDDEN_JSON_KEYS = (
    '"target_answers"',
    '"rule_index"',
    '"private_state"',
    '"seed"',
    '"hint_category"',
    '"correct_option"',
    '"expected_holes"',
    '"witness"',
    '"certificate"',
    '"exam_effects"',
    '"matrix"',
)


def _task(family: str, *, seed: int = 11, difficulty: int = 2) -> TaskInstance:
    generated = generate_task(
        family=family,
        generator_version=generator_version_for(family),
        seed=seed,
        difficulty=difficulty,
    )
    return TaskInstance(
        id=f"test-{family}-{seed}",
        attempt_id="attempt-test",
        ordinal=1,
        family=family,
        generator_version=generator_version_for(family),
        seed=seed,
        difficulty=difficulty,
        public_state=generated.public_state,
        private_state=generated.private_state,
    )


def test_graph_context_contains_all_visible_vertices():
    task = _task("geo_zendo")
    context = build_task_context(task, [])
    scene_points = task.public_state["scene"]["points"]
    context_vertices = [
        vertex
        for card in context.payload["visibleState"]["cards"]
        for vertex in card["vertices"]
    ]
    assert len(context_vertices) == len(scene_points)
    assert {vertex["label"] for vertex in context_vertices} == {
        point["label"] for point in scene_points
    }


def test_graph_context_contains_all_visible_edges():
    task = _task("geo_zendo")
    context = build_task_context(task, [])
    scene_edges = task.public_state["scene"]["edges"]
    context_edges = [
        edge
        for card in context.payload["visibleState"]["cards"]
        for edge in card["edges"]
    ]
    assert len(context_edges) == len(scene_edges)


def test_graph_context_roles_and_example_classifications():
    task = _task("geo_zendo")
    context = build_task_context(task, [])
    cards = {card["id"]: card for card in context.payload["visibleState"]["cards"]}
    examples = task.public_state["content"]["examples"]
    for example in examples:
        card = cards[example["card_id"]]
        assert card["role"] in {"positive_example", "negative_example"}
        assert card["classification"] in {"подходит", "не подходит"}
    for target in task.public_state["content"]["targets"]:
        assert cards[target["card_id"]]["role"] == "target"
        assert cards[target["card_id"]]["classification"] is None


def test_graph_context_does_not_contain_unrevealed_probe_result():
    task = _task("geo_zendo")
    context = build_task_context(task, [])
    for card in context.payload["visibleState"]["cards"]:
        if card["role"] == "available_probe":
            assert card["classification"] is None


def test_graph_context_contains_revealed_probe_result_and_changes_after_probe():
    task = _task("geo_zendo")
    before = build_task_context(task, [])
    probe_id = task.public_state["content"]["probe_cards"][0]["card_id"]
    transition = transition_geo_zendo_v2_probe(
        card_id=probe_id,
        public_state=task.public_state,
        private_state=task.private_state,
    )
    assert transition.accepted
    task.public_state = transition.public_state
    after = build_task_context(task, [])
    assert after.sha256 != before.sha256
    cards = {card["id"]: card for card in after.payload["visibleState"]["cards"]}
    assert cards[probe_id]["role"] == "tested_probe"
    assert cards[probe_id]["classification"] in {"подходит", "не подходит"}


def test_graph_context_does_not_contain_hidden_rule_or_private_state():
    for family in (
        "geo_zendo",
        "token_zendo",
        "point_zendo",
        "grid_zendo",
        "hidden_wiring",
        "machine_reach",
        "fold_punch",
        "dice_chess",
        "geo_transform",
        "geo_probability",
    ):
        task = _task(family)
        context = build_task_context(task, [])
        for forbidden in FORBIDDEN_JSON_KEYS:
            assert forbidden not in context.canonical_json, (family, forbidden)


def test_graph_context_hash_is_deterministic():
    first = build_task_context(_task("geo_zendo"), [])
    second = build_task_context(_task("geo_zendo"), [])
    assert first.sha256 == second.sha256
    assert first.canonical_json == second.canonical_json
    assert (
        json.loads(first.canonical_json)["task"]["family"] == "geo_zendo"
    )


def test_chess_context_contains_board_and_dice():
    task = _task("dice_chess")
    context = build_task_context(task, [])
    visible = context.payload["visibleState"]
    assert "board" in visible
    assert "die" in visible or "dice" in visible
    assert visible.get("event_description")


def test_machine_context_has_states_but_no_solution():
    task = _task("machine_reach", seed=3)
    context = build_task_context(task, [])
    visible = context.payload["visibleState"]
    assert "start" in visible and "current" in visible
    assert '"reachable"' not in context.canonical_json
    assert '"witness"' not in context.canonical_json


def test_wiring_context_shows_observations_only():
    task = _task("hidden_wiring", seed=5, difficulty=1)
    context = build_task_context(task, [])
    visible = context.payload["visibleState"]
    assert visible["lampCount"] == task.public_state["lamp_count"]
    assert visible["observations"] == []
    assert '"matrix"' not in context.canonical_json
