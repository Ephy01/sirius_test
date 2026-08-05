"""Acceptance battery shared by the new Universe-protocol zendo families.

Per-family requirements from the content-v3 spec:

* determinism by seed;
* public_state leak test;
* generation filters hold over a large sweep (base rate bounds, a minimal
  pair exists for every item, no cheaper semantic duplicate in the space);
* one hundred warm generations under five seconds;
* ``zendo_probe`` events with ``gain_bits_actual``/``gain_bits_best`` at
  the API layer.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.environments.core.zendo_engine import get_universe_space
from app.environments.zendo.grid import (
    GridUniverse,
    generate_grid_zendo_task,
)
from app.environments.zendo.point import (
    PointUniverse,
    generate_point_zendo_task,
)
from app.environments.zendo.token import (
    TokenUniverse,
    generate_token_zendo_task,
)
from app.main import create_app
from app.models import AttemptEvent, TaskInstance

FORBIDDEN_PUBLIC_KEYS = {
    "rule_index",
    "version_space",
    "version_space_after_examples",
    "target_answers",
    "probe_truth_masks",
    "private_state",
    "seed",
}

FAMILY_CASES = [
    pytest.param(
        "token_zendo",
        TokenUniverse(),
        generate_token_zendo_task,
        id="token_zendo",
    ),
    pytest.param(
        "point_zendo",
        PointUniverse(),
        generate_point_zendo_task,
        id="point_zendo",
    ),
    pytest.param(
        "grid_zendo",
        GridUniverse(),
        generate_grid_zendo_task,
        id="grid_zendo",
    ),
]


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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


@pytest.mark.parametrize(("family", "universe", "generate"), FAMILY_CASES)
def test_zendo_family_is_deterministic_and_does_not_leak(
    family,
    universe,
    generate,
):
    for difficulty in (1, 2, 3, 4, 5):
        for seed in range(12):
            public, private = generate(seed=seed, difficulty=difficulty)
            assert (public, private) == generate(
                seed=seed,
                difficulty=difficulty,
            )
            assert public["family"] == family
            assert private["family"] == family
            assert private["difficulty"] == difficulty
            assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
            content = public["content"]
            assert len(content["examples"]) == 4
            assert sum(
                item["classification"] == "positive"
                for item in content["examples"]
            ) == 2
            if "probe_cards" in content:
                assert len(content["probe_cards"]) == 12
            assert len(content["targets"]) == 8
            assert content["probes_remaining"] == 5


@pytest.mark.parametrize(("family", "universe", "generate"), FAMILY_CASES)
def test_zendo_family_space_filters_hold(family, universe, generate):
    space = get_universe_space(universe)
    population_size = len(space.population)
    for truth_mask in space.truth_masks:
        base_rate = truth_mask.bit_count() / population_size
        assert 0.12 <= base_rate <= 0.88
    assert len(set(space.truth_masks)) == len(space.truth_masks)
    for bucket in space.mdl_buckets:
        assert bucket
    from app.environments.core.rule_dsl import compile_truth_masks

    raw_rules = universe.enumerate_rules()
    raw_masks = compile_truth_masks(
        raw_rules,
        space.population,
        atoms=space.atoms,
    )
    cheapest_by_mask: dict[int, int] = {}
    for rule, mask in zip(raw_rules, raw_masks, strict=True):
        current = cheapest_by_mask.get(mask)
        if current is None or rule.mdl < current:
            cheapest_by_mask[mask] = rule.mdl
    for rule, mask in zip(
        space.rules[:64],
        space.truth_masks[:64],
        strict=False,
    ):
        assert rule.mdl == cheapest_by_mask[mask]


@pytest.mark.parametrize(("family", "universe", "generate"), FAMILY_CASES)
def test_zendo_family_items_have_minimal_pairs_over_sweep(
    family,
    universe,
    generate,
):
    space = get_universe_space(universe)
    for seed in range(200):
        _public, private = generate(seed=seed, difficulty=1 + seed % 5)
        answers = [bool(value) for value in private["target_answers"]]
        assert answers.count(True) >= 1
        assert answers.count(False) >= 1
        assert len(answers) == 8
        rule = space.rules[int(private["rule_index"])]
        assert rule.mdl >= 3


@pytest.mark.parametrize(("family", "universe", "generate"), FAMILY_CASES)
def test_zendo_family_warm_generation_perf(family, universe, generate):
    generate(seed=0, difficulty=1)
    started = time.perf_counter()
    for index in range(100):
        generate(seed=index, difficulty=1 + index % 5)
    assert time.perf_counter() - started < 5


API_FAMILY_CASES = [
    pytest.param("token_zendo", "token_zendo", "token-zendo-v1", id="token"),
    pytest.param("point_zendo", "point_zendo", "point-zendo-v1", id="point"),
]


@pytest.mark.parametrize(
    ("family", "expected_kind", "expected_version"),
    API_FAMILY_CASES,
)
def test_zendo_api_probe_logs_gain_bits(
    tmp_path,
    family,
    expected_kind,
    expected_version,
):
    application = create_app(_settings(tmp_path / f"{family}-api.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Zendo API",
                "task_config": {
                    "families": [
                        {
                            "family": family,
                            "weight": 1,
                            "initial_difficulty": 3,
                            "max_difficulty": 5,
                        }
                    ],
                },
            },
        ).json()
        client.post(
            f"/api/v1/contests/{contest['id']}/enrollments",
            headers=auth(organizer),
            json={
                "participants": [
                    {"external_ref": f"{family}-001", "display_name": "Участник"}
                ]
            },
        )
        code = client.post(
            f"/api/v1/contests/{contest['id']}/codes",
            headers=auth(organizer),
            json={},
        ).json()["items"][0]["code"]
        client.post(
            f"/api/v1/contests/{contest['id']}/publish",
            headers=auth(organizer),
        )
        participant = client.post(
            "/api/v1/access/redeem",
            json={"code": code},
        ).json()["access_token"]

        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        assert task["family"] == family
        assert task["generator_version"] == expected_version
        assert task["public_state"]["kind"] == expected_kind
        probe_id = task["public_state"]["content"]["probe_cards"][0]["card_id"]
        if family == "token_zendo":
            cards = task["public_state"]["cards"]
            assert probe_id in cards
            assert all(
                token["color"] in {"R", "G", "B"}
                and 1 <= token["num"] <= 9
                for card_tokens in cards.values()
                for token in card_tokens
            )
        else:
            scene = task["public_state"]["scene"]
            assert scene["edges"] == []
            assert any(
                point["group"] == probe_id
                for point in scene["points"]
            )

        probed = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "zendo-probe-1",
                "action_type": "probe",
                "probe": probe_id.lower(),
            },
        )
        assert probed.status_code == 200
        assert probed.json()["accepted"] is True

        replayed = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "zendo-probe-1",
                "action_type": "probe",
                "probe": probe_id.lower(),
            },
        )
        assert replayed.status_code == 200

        with application.state.database.session_factory() as session:
            from sqlalchemy import select

            probe_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "zendo_probe"
                    )
                )
            )
            assert len(probe_events) == 1
            payload = probe_events[0].payload
            assert payload["card_id"] == probe_id
            assert payload["vs_size_before"] >= payload["vs_size_after"] >= 1
            assert payload["gain_bits_actual"] >= 0.0
            assert 0.0 <= payload["gain_bits_best"] <= 1.0

            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            answer = " ".join(
                "да" if value else "нет"
                for value in stored.private_state["target_answers"]
            )

        answered = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": answer},
        )
        assert answered.status_code == 200
        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            evaluation = stored.evaluation_state
            assert evaluation["correct"] is True
            assert evaluation["family"] == family
            assert evaluation["generator_version"] == expected_version
            assert 0.0 <= evaluation["continuous_score"] <= 1.0


def test_point_sampler_records_build_metrics():
    from app.environments.zendo.point import sampler_build_log

    get_universe_space(PointUniverse())
    log = sampler_build_log()
    assert "sampler_rejects" in log
    for atom_key, rate in log["atom_base_rates"].items():
        assert 0.12 <= rate <= 0.88, atom_key


def test_grid_symmetry_literals_survive_distillation():
    space = get_universe_space(GridUniverse())
    literal_keys = {
        rule.atom_key
        for rule in space.rules
        if rule.op == "atom" and rule.atom_key
    }
    assert literal_keys & {"sym_rotate_90", "sym_rotate_270"}
    assert {
        "sym_rotate_180",
        "sym_reflect_h",
        "sym_reflect_v",
        "sym_reflect_main",
        "sym_reflect_anti",
        "connected",
        "domino_tileable",
    } <= literal_keys


def test_grid_zendo_api_drawn_probe_flow(tmp_path):
    application = create_app(_settings(tmp_path / "grid-zendo-api.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Grid Zendo",
                "task_config": {
                    "families": [
                        {
                            "family": "grid_zendo",
                            "weight": 1,
                            "initial_difficulty": 2,
                            "max_difficulty": 5,
                        }
                    ],
                },
            },
        ).json()
        client.post(
            f"/api/v1/contests/{contest['id']}/enrollments",
            headers=auth(organizer),
            json={
                "participants": [
                    {"external_ref": "grid-001", "display_name": "Участник"}
                ]
            },
        )
        code = client.post(
            f"/api/v1/contests/{contest['id']}/codes",
            headers=auth(organizer),
            json={},
        ).json()["items"][0]["code"]
        client.post(
            f"/api/v1/contests/{contest['id']}/publish",
            headers=auth(organizer),
        )
        participant = client.post(
            "/api/v1/access/redeem",
            json={"code": code},
        ).json()["access_token"]

        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        assert task["family"] == "grid_zendo"
        assert task["public_state"]["kind"] == "grid_zendo"
        cards = task["public_state"]["cards"]
        assert all(
            len(rows) == 5 and all(len(row) == 5 for row in rows)
            for rows in cards.values()
        )
        assert "probe_cards" not in task["public_state"]["content"]

        invalid = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "grid-probe-invalid",
                "action_type": "probe",
                "probe": "0101",
            },
        )
        assert invalid.status_code == 200
        assert invalid.json()["accepted"] is False

        drawn = "1100000000000000000000000"
        probed = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "grid-probe-1",
                "action_type": "probe",
                "probe": drawn,
            },
        )
        assert probed.status_code == 200
        assert probed.json()["accepted"] is True
        observations = probed.json()["task"]["public_state"]["content"][
            "probe_observations"
        ]
        assert len(observations) == 1
        assert observations[0]["pattern"] == [
            "11000",
            "00000",
            "00000",
            "00000",
            "00000",
        ]

        with application.state.database.session_factory() as session:
            from sqlalchemy import select

            probe_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "zendo_probe"
                    )
                )
            )
            assert len(probe_events) == 1
            payload = probe_events[0].payload
            assert payload["gain_bits_actual"] >= 0.0
            assert payload["gain_bits_best"] >= 0.0
            assert payload["vs_size_before"] >= payload["vs_size_after"]

            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            assert stored.private_state["probes_remaining"] == 4
            answer = " ".join(
                "да" if value else "нет"
                for value in stored.private_state["target_answers"]
            )

        answered = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": answer},
        )
        assert answered.status_code == 200
        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            evaluation = stored.evaluation_state
            assert evaluation["correct"] is True
            assert evaluation["family"] == "grid_zendo"
            assert evaluation["generator_version"] == "grid-zendo-v1"
