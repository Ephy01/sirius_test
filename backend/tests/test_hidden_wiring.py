"""Acceptance battery for the hidden_wiring family (stage W)."""

from __future__ import annotations

from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.environments.wiring import (
    CHORD_BUDGET,
    PREDICT_VARIANT,
    REACH_VARIANT,
    evaluate_hidden_wiring_answer,
    generate_hidden_wiring_task,
    transition_hidden_wiring_chord,
    validate_hidden_wiring_instance,
)
from app.main import create_app
from app.models import AttemptEvent, TaskInstance

FORBIDDEN_PUBLIC_KEYS = {
    "columns",
    "chord_effects",
    "certificate",
    "exam_effects",
    "min_len",
    "private_state",
    "seed",
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


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def test_wiring_is_deterministic_solvable_and_does_not_leak():
    variants: dict[str, int] = {}
    for seed in range(1000):
        difficulty = 1 + seed % 5
        public, private = generate_hidden_wiring_task(
            seed=seed,
            difficulty=difficulty,
        )
        assert (public, private) == generate_hidden_wiring_task(
            seed=seed,
            difficulty=difficulty,
        )
        validate_hidden_wiring_instance(public, private)
        variants[private["variant"]] = variants.get(private["variant"], 0) + 1
        assert _nested_keys(public).isdisjoint(FORBIDDEN_PUBLIC_KEYS)
        assert public["legend"] == "Кнопки срабатывают только парами."
        assert public["chords_remaining"] == CHORD_BUDGET
        if private["variant"] == REACH_VARIANT:
            # Variant (а) always solvable, certificate stored in private.
            assert private["certificate"]
            assert len(private["certificate"]) <= CHORD_BUDGET
        else:
            exam_ids = {item["id"] for item in public["exam_chords"]}
            op_ids = {item["id"] for item in public["ops"]}
            assert not exam_ids & op_ids
    assert variants[REACH_VARIANT] > 100
    assert variants[PREDICT_VARIANT] > 100


def test_chords_are_idempotent_pure_and_carry_exact_gain_bits():
    public, private = generate_hidden_wiring_task(seed=11, difficulty=1)
    assert private["variant"] == REACH_VARIANT
    original_public = deepcopy(public)
    original_private = deepcopy(private)
    chord = private["certificate"][0]

    first = transition_hidden_wiring_chord(
        op_id=chord,
        public_state=public,
        private_state=private,
        client_action_id="chord-1",
    )
    # Pure transition: inputs must stay unmutated.
    assert public == original_public
    assert private == original_private
    assert first.accepted is True
    telemetry = first.evaluation_state
    lamp_count = private["lamp_count"]
    button_count = private["button_count"]
    assert telemetry["vs_size_before"] == 1 << (
        lamp_count * (button_count - 1)
    )
    assert telemetry["gain_bits_actual"] == float(lamp_count)
    assert telemetry["gain_bits_best"] == float(lamp_count)
    # The first probe is a free training one.
    assert first.public_state["chords_remaining"] == CHORD_BUDGET
    assert first.public_state["observations"][0]["training"] is True

    replayed = transition_hidden_wiring_chord(
        op_id=chord,
        public_state=first.public_state,
        private_state=first.private_state,
        client_action_id="chord-1",
    )
    assert replayed.accepted is first.accepted
    assert replayed.public_state == first.public_state
    assert replayed.private_state == first.private_state

    try:
        transition_hidden_wiring_chord(
            op_id="b9+b9",
            public_state=first.public_state,
            private_state=first.private_state,
            client_action_id="chord-1",
        )
    except ValueError as error:
        assert "already used" in str(error)
    else:  # pragma: no cover - защита от регрессии
        raise AssertionError("reused client_action_id must raise")

    # A dependent chord repeat yields zero information.
    second = transition_hidden_wiring_chord(
        op_id=chord,
        public_state=first.public_state,
        private_state=first.private_state,
        client_action_id="chord-2",
    )
    assert second.evaluation_state["gain_bits_actual"] == 0.0
    assert second.public_state["chords_remaining"] == CHORD_BUDGET - 1


def test_reach_variant_completes_on_target_and_scores_length():
    public, private = generate_hidden_wiring_task(seed=11, difficulty=1)
    assert private["variant"] == REACH_VARIANT
    state_public, state_private = public, private
    for index, chord in enumerate(private["certificate"]):
        transition = transition_hidden_wiring_chord(
            op_id=chord,
            public_state=state_public,
            private_state=state_private,
            client_action_id=f"chord-{index}",
        )
        assert transition.accepted is True
        state_public, state_private = (
            transition.public_state,
            transition.private_state,
        )
    assert transition.completed is True
    evaluation = transition.evaluation_state
    assert evaluation["correct"] is True
    assert evaluation["continuous_score"] == 1.0
    assert evaluation["efficient"] is True

    # /answer never finalizes the reach variant on its own.
    answered = evaluate_hidden_wiring_answer(
        answer="done",
        private_state=private,
    )
    assert answered["should_finalize"] is False


def test_predict_variant_scores_bitwise_accuracy():
    public, private = None, None
    for seed in range(50):
        candidate_public, candidate_private = generate_hidden_wiring_task(
            seed=seed,
            difficulty=5,
        )
        if candidate_private["variant"] == PREDICT_VARIANT:
            public, private = candidate_public, candidate_private
            break
    assert private is not None
    lamp_count = private["lamp_count"]
    exact_answer = " ".join(
        "".join(
            "1" if (effect >> index) & 1 else "0"
            for index in range(lamp_count)
        )
        for effect in private["exam_effects"]
    )
    exact = evaluate_hidden_wiring_answer(
        answer=exact_answer,
        private_state=private,
    )
    assert exact["correct"] is True
    assert exact["continuous_score"] == 1.0
    assert exact["evidence"] == 1

    malformed = evaluate_hidden_wiring_answer(
        answer="не знаю",
        private_state=private,
    )
    assert malformed["parsed"] is False
    assert malformed["should_finalize"] is False

    wrong = evaluate_hidden_wiring_answer(
        answer=" ".join("0" * lamp_count for _ in range(3)),
        private_state=private,
    )
    assert wrong["correct"] is False
    assert 0.0 <= wrong["continuous_score"] <= 1.0
    assert wrong["evidence"] == -1


def test_wiring_api_chords_log_zendo_probe_events(tmp_path):
    application = create_app(_settings(tmp_path / "wiring-api.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Hidden Wiring",
                "task_config": {
                    "families": [
                        {
                            "family": "hidden_wiring",
                            "weight": 1,
                            "initial_difficulty": 1,
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
                    {"external_ref": "wiring-001", "display_name": "Участник"}
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
        assert task["family"] == "hidden_wiring"
        assert task["public_state"]["kind"] == "hidden_wiring"

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            certificate = list(stored.private_state["certificate"])

        current = task
        for index, chord in enumerate(certificate):
            response = client.post(
                f"/api/v1/participant/tasks/{task['id']}/interactions",
                headers=auth(participant),
                json={
                    "client_action_id": f"api-chord-{index}",
                    "action_type": "apply_op",
                    "op_id": chord,
                },
            )
            assert response.status_code == 200
            assert response.json()["accepted"] is True
            current = response.json()["task"]
        assert current["status"] == "answered"

        # Idempotent replay of the completing chord.
        replay = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": f"api-chord-{len(certificate) - 1}",
                "action_type": "apply_op",
                "op_id": certificate[-1],
            },
        )
        assert replay.status_code == 200
        assert replay.json()["completed"] is True

        with application.state.database.session_factory() as session:
            probe_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "zendo_probe"
                    )
                )
            )
            assert len(probe_events) == len(certificate)
            for event in probe_events:
                assert event.payload["gain_bits_actual"] >= 0.0
                assert event.payload["vs_size_before"] >= 1

            stored = session.get(TaskInstance, task["id"])
            evaluation = stored.evaluation_state
            assert evaluation["correct"] is True
            assert evaluation["family"] == "hidden_wiring"
            assert evaluation["generator_version"] == "hidden-wiring-v1"
            assert evaluation["director_signal"] in {"strong", "pass"}
