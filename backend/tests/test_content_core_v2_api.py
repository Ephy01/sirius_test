from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.environments import (
    MACHINE_REACH_FAMILY,
    MACHINE_REACH_GENERATOR_VERSION,
    derive_task_seed,
)
from app.environments.machines import generate_machine_reach_task
from app.main import create_app
from app.models import Attempt, AttemptEvent, TaskInstance, TaskInteraction, utc_now


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def prepare_contest(
    client: TestClient,
    *,
    families: list[dict],
    participants: int = 1,
    cohort_seed: str | None = None,
    adaptive: bool = False,
) -> tuple[dict, list[str]]:
    organizer = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    ).json()["access_token"]
    task_config: dict = {"families": families}
    if cohort_seed is not None:
        task_config["cohort_seed"] = cohort_seed
    if adaptive:
        task_config["trajectory"] = {
            "mode": "adaptive",
            "director_version": "director-v2",
        }
    created = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Content core v2",
            "environment_key": "mixed",
            "task_config": task_config,
        },
    )
    assert created.status_code == 201
    contest = created.json()
    assert contest["environment_key"] == "mixed"
    enrolled = client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {
                    "external_ref": f"core-v2-{index}",
                    "display_name": f"Участник {index}",
                }
                for index in range(participants)
            ]
        },
    )
    assert enrolled.status_code == 201
    codes = client.post(
        f"/api/v1/contests/{contest['id']}/codes",
        headers=auth(organizer),
        json={},
    ).json()["items"]
    assert client.post(
        f"/api/v1/contests/{contest['id']}/publish",
        headers=auth(organizer),
    ).status_code == 200
    tokens = [
        client.post(
            "/api/v1/access/redeem",
            json={"code": item["code"]},
        ).json()["access_token"]
        for item in codes
    ]
    return contest, tokens


def nested_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            key
            for item in value.values()
            for key in nested_keys(item)
        }
    if isinstance(value, list):
        return {key for item in value for key in nested_keys(item)}
    return set()


def test_machine_reach_api_is_idempotent_and_freezes_false_impossible(tmp_path):
    application = create_app(settings(tmp_path / "machine-api.db"))
    with TestClient(application) as client:
        _contest, tokens = prepare_contest(
            client,
            families=[
                {
                    "family": MACHINE_REACH_FAMILY,
                    "skin": "panel",
                    "sub_kinds": ["lamps_gf2"],
                    "weight": 1,
                    "initial_difficulty": 2,
                    "max_difficulty": 5,
                }
            ],
        )
        participant = tokens[0]
        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        ).json()["attempt"]

        reachable_seed = next(
            attempt_seed
            for attempt_seed in range(1, 10_000)
            if generate_machine_reach_task(
                seed=derive_task_seed(
                    attempt_seed,
                    1,
                    MACHINE_REACH_FAMILY,
                    MACHINE_REACH_GENERATOR_VERSION,
                ),
                difficulty=2,
                sub_kind="lamps_gf2",
            )[1]["reachable"]
        )
        with application.state.database.session_factory() as session:
            attempt = session.get(Attempt, started["id"])
            assert attempt is not None
            attempt.seed = reachable_seed
            session.commit()

        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        assert task["public_state"]["kind"] == "machine_panel"
        assert task["public_state"]["sub_kind"] == "lamps_gf2"
        assert nested_keys(task["public_state"]).isdisjoint(
            {"reachable", "witness", "certificate", "min_len", "private_state"}
        )

        false_claim = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": "impossible"},
        )
        assert false_claim.status_code == 200
        assert false_claim.json()["task"]["status"] == "active"

        frozen = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "frozen-op",
                "action_type": "apply_op",
                "op_id": task["public_state"]["ops"][0]["id"],
            },
        )
        assert frozen.status_code == 429
        assert frozen.json()["detail"]["code"] == "TASK_INPUT_FROZEN"

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            witness = list(stored.private_state["witness"])
            stored.private_state = {
                **stored.private_state,
                "input_frozen_until": (
                    utc_now() - timedelta(seconds=1)
                ).isoformat(),
            }
            session.commit()

        first_payload = {
            "client_action_id": "solve-1",
            "action_type": "apply_op",
            "op_id": witness[0],
        }
        first = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json=first_payload,
        )
        assert first.status_code == 200
        assert first.json()["accepted"] is True
        repeated = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json=first_payload,
        )
        assert repeated.status_code == 200
        assert repeated.json()["task"]["public_state"]["steps_taken"] == 1

        for index, op_id in enumerate(witness[1:], start=2):
            applied = client.post(
                f"/api/v1/participant/tasks/{task['id']}/interactions",
                headers=auth(participant),
                json={
                    "client_action_id": f"solve-{index}",
                    "action_type": "apply_op",
                    "op_id": op_id,
                },
            )
            assert applied.status_code == 200
            assert applied.json()["accepted"] is True

        completed = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": "done"},
        )
        assert completed.status_code == 200
        assert completed.json()["task"]["status"] == "answered"

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            evaluation = stored.evaluation_state
            assert evaluation["continuous_score"] > 0
            assert evaluation["family"] == MACHINE_REACH_FAMILY
            assert evaluation["generator_version"] == MACHINE_REACH_GENERATOR_VERSION
            assert evaluation["difficulty"] == 2
            assert "first_action_latency_ms" in evaluation
            assert "undo_count" in evaluation
            assert "revisited_states" in evaluation
            assert "len_ratio" in evaluation
            assert evaluation["false_impossible"] is False
            interactions = list(
                session.scalars(
                    select(TaskInteraction).where(
                        TaskInteraction.task_instance_id == task["id"]
                    )
                )
            )
            assert len(interactions) == len(witness)
            events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.task_instance_id == task["id"]
                    )
                )
            )
            assert any(event.event_type == "task_input_frozen" for event in events)
            false_impossible_event = next(
                event
                for event in events
                if event.event_type == "answer_evaluated"
                and event.payload.get("false_impossible") is True
            )
            assert isinstance(
                false_impossible_event.payload.get("first_action_latency_ms"),
                int,
            )


def test_cohort_seed_reproduces_nim_trajectory_and_logs_regret(tmp_path):
    application = create_app(settings(tmp_path / "nim-cohort.db"))
    with TestClient(application) as client:
        _contest, tokens = prepare_contest(
            client,
            participants=2,
            cohort_seed="wave-july-2026",
            adaptive=True,
            families=[
                {
                    "family": "nim_like",
                    "skin": "counters",
                    "weight": 1,
                    "initial_difficulty": 3,
                    "max_difficulty": 5,
                }
            ],
        )
        attempts = [
            client.post(
                "/api/v1/participant/attempts/start",
                headers=auth(token),
            ).json()["attempt"]
            for token in tokens
        ]
        tasks = [
            client.get(
                "/api/v1/participant/tasks/current",
                headers=auth(token),
            ).json()["task"]
            for token in tokens
        ]
        participant_context = client.get(
            "/api/v1/participant/context",
            headers=auth(tokens[0]),
        )
        assert participant_context.status_code == 200
        serialized_context = participant_context.json()
        assert "task_config" not in serialized_context["contest"]
        assert "wave-july-2026" not in participant_context.text
        assert tasks[0]["public_state"] == tasks[1]["public_state"]
        assert nested_keys(tasks[0]["public_state"]).isdisjoint(
            {
                "winning",
                "winning_moves",
                "legal_moves",
                "grundy_values",
                "nim_sum",
                "private_state",
            }
        )
        with application.state.database.session_factory() as session:
            stored_attempts = [
                session.get(Attempt, attempt["id"]) for attempt in attempts
            ]
            assert all(item is not None for item in stored_attempts)
            assert stored_attempts[0].seed == stored_attempts[1].seed
            stored_task = session.get(TaskInstance, tasks[0]["id"])
            assert stored_task is not None
            if stored_task.private_state["winning"]:
                move = stored_task.private_state["winning_moves"][0]
                answer = f"take {move['heap']} {move['count']}"
            else:
                answer = "проигрышная"

        for token, task in zip(tokens, tasks, strict=True):
            answered = client.post(
                f"/api/v1/participant/tasks/{task['id']}/answer",
                headers=auth(token),
                json={"answer": answer},
            )
            assert answered.status_code == 200
            assert answered.json()["task"]["status"] == "answered"

        next_tasks = [
            client.post(
                "/api/v1/participant/tasks/next",
                headers=auth(token),
            ).json()["task"]
            for token in tokens
        ]
        assert next_tasks[0]["public_state"] == next_tasks[1]["public_state"]
        with application.state.database.session_factory() as session:
            stored_next_tasks = [
                session.get(TaskInstance, task["id"])
                for task in next_tasks
            ]
            assert all(task is not None for task in stored_next_tasks)
            assert stored_next_tasks[0].seed == stored_next_tasks[1].seed

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, tasks[0]["id"])
            assert stored is not None
            evaluation = stored.evaluation_state
            assert evaluation["correct"] is True
            assert evaluation["regret"] == 0
            assert evaluation["continuous_score"] == 1
            assert evaluation["difficulty"] == 3
            assert evaluation["family"] == "nim_like"
            assert evaluation["generator_version"] == "nim-like-v1"


def test_mixed_contest_uses_zendo_v2_and_logs_probe_information(tmp_path):
    application = create_app(settings(tmp_path / "zendo-v2-api.db"))
    with TestClient(application) as client:
        _contest, tokens = prepare_contest(
            client,
            families=[
                {
                    "family": "geo_zendo",
                    "skin": "graph",
                    "weight": 1,
                    "initial_difficulty": 3,
                    "max_difficulty": 5,
                }
            ],
        )
        participant = tokens[0]
        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        assert task["generator_version"] == "geometry-zendo-v2"
        assert task["public_state"]["dsl_version"] == "graph-dsl-v1"
        assert len(task["public_state"]["content"]["targets"]) == 8
        assert nested_keys(task["public_state"]).isdisjoint(
            {
                "rule_index",
                "version_space",
                "target_answers",
                "probe_truth_masks",
            }
        )

        card_id = task["public_state"]["content"]["probe_cards"][0]["card_id"]
        payload = {
            "client_action_id": "zendo-probe-1",
            "action_type": "probe",
            "probe": card_id,
        }
        probed = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json=payload,
        )
        assert probed.status_code == 200
        assert probed.json()["accepted"] is True
        repeated = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json=payload,
        )
        assert repeated.status_code == 200

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            answer = " ".join(
                "да" if value else "нет"
                for value in stored.private_state["target_answers"]
            )
            probe_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.task_instance_id == task["id"],
                        AttemptEvent.event_type == "zendo_probe",
                    )
                )
            )
            assert len(probe_events) == 1
            telemetry = probe_events[0].payload
            assert telemetry["vs_size_before"] >= telemetry["vs_size_after"] >= 1
            assert telemetry["gain_bits_actual"] >= 0
            assert telemetry["gain_bits_best"] >= 0

        answered = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": answer},
        )
        assert answered.status_code == 200
        assert answered.json()["task"]["status"] == "answered"
        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            assert stored.evaluation_state["continuous_score"] == 1
            assert stored.evaluation_state["difficulty"] == 3
            assert stored.evaluation_state["family"] == "geo_zendo"
            assert (
                stored.evaluation_state["generator_version"]
                == "geometry-zendo-v2"
            )
