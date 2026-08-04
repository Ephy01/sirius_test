from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import Attempt, AttemptEvent, TaskInstance


GEOMETRY_GENERATOR_VERSION = "geometry-atlas-v1"
GEOMETRY_DIRECTOR_VERSION = "geometry-world-director-v1"
GEOMETRY_PRIVATE_KEYS = {
    "private_state",
    "rule_key",
    "available_rule_keys",
    "consistent_rule_keys_after_examples",
    "truth_by_card",
    "probe_card_ids",
    "used_probe_card_ids",
    "target_card_ids",
    "target_answers",
}


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _nested_keys(value) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {
            nested_key
            for nested_value in value.values()
            for nested_key in _nested_keys(nested_value)
        }
    if isinstance(value, list):
        return {
            nested_key
            for nested_value in value
            for nested_key in _nested_keys(nested_value)
        }
    return set()


def _settings(database_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def _geometry_config(
    *,
    families: list[dict],
    start_family: str,
) -> dict:
    return {
        "adaptation_threshold": 3,
        "trajectory": {
            "mode": "adaptive",
            "director_version": GEOMETRY_DIRECTOR_VERSION,
            "start_family": start_family,
        },
        "families": families,
    }


def _create_geometry_participant(
    client: TestClient,
    *,
    external_ref: str,
    families: list[dict],
    start_family: str,
) -> tuple[str, dict, str]:
    organizer_response = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    )
    assert organizer_response.status_code == 200
    organizer = organizer_response.json()["access_token"]

    contest_response = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Геометрический атлас",
            "duration_minutes": 60,
            "environment_key": "geometry_world",
            "task_config": _geometry_config(
                families=families,
                start_family=start_family,
            ),
        },
    )
    assert contest_response.status_code == 201
    contest = contest_response.json()
    assert contest["environment_key"] == "geometry_world"
    assert contest["status"] == "draft"

    enrollment_response = client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {
                    "external_ref": external_ref,
                    "display_name": "Тестовый участник",
                }
            ]
        },
    )
    assert enrollment_response.status_code == 201
    enrollment = enrollment_response.json()["items"][0]

    code_response = client.post(
        f"/api/v1/contests/{contest['id']}/codes",
        headers=auth(organizer),
        json={},
    )
    assert code_response.status_code == 200
    generated = code_response.json()
    assert generated["generated_count"] == 1
    code_item = generated["items"][0]
    assert code_item["enrollment_id"] == enrollment["id"]
    assert code_item["participant"]["external_ref"] == external_ref
    participant_code = code_item["code"]

    publish_response = client.post(
        f"/api/v1/contests/{contest['id']}/publish",
        headers=auth(organizer),
    )
    assert publish_response.status_code == 200
    assert publish_response.json()["status"] == "published"

    redeem_response = client.post(
        "/api/v1/access/redeem",
        json={"code": participant_code},
    )
    assert redeem_response.status_code == 200
    assert redeem_response.json()["role"] == "participant"
    participant = redeem_response.json()["access_token"]
    return participant, contest, participant_code


def _correct_geometry_answer(application, task_id: str) -> str:
    with application.state.database.session_factory() as session:
        task = session.get(TaskInstance, task_id)
        assert task is not None
        private = task.private_state
        if task.family == "geo_transform":
            return str(private["correct_card_id"])
        if task.family == "geo_probability":
            probability = private["probability"]
            return f"{probability['numerator']}/{probability['denominator']}"
        if task.family == "geo_zendo":
            return " ".join(
                "да" if value else "нет"
                for value in private["target_answers"]
            )
    raise AssertionError(f"No test answer helper for family {task.family!r}")


def _answer_geometry_task(
    client: TestClient,
    application,
    participant: str,
    task: dict,
) -> None:
    response = client.post(
        f"/api/v1/participant/tasks/{task['id']}/answer",
        headers=auth(participant),
        json={"answer": _correct_geometry_answer(application, task["id"])},
    )
    assert response.status_code == 200
    assert response.json()["task"]["status"] == "answered"
    assert "evaluation_state" not in response.json()["task"]

    with application.state.database.session_factory() as session:
        stored = session.get(TaskInstance, task["id"])
        assert stored is not None
        assert stored.evaluation_state["correct"] is True
        assert stored.evaluation_state["director_signal"] == "strong"


def test_geometry_world_complete_api_flow_answer_skip_and_next(tmp_path):
    application = create_app(_settings(tmp_path / "geometry-flow.db"))
    family = {
        "key": "geo_transform",
        "enabled": True,
        "weight": 1,
        "initial_difficulty": 1,
        "max_difficulty": 4,
    }

    with TestClient(application) as client:
        participant, contest, participant_code = _create_geometry_participant(
            client,
            external_ref="geometry-flow-001",
            families=[family],
            start_family="geo_transform",
        )
        assert participant_code.startswith("SG-")

        context = client.get(
            "/api/v1/participant/context",
            headers=auth(participant),
        )
        assert context.status_code == 200
        assert context.json()["contest"]["id"] == contest["id"]
        assert context.json()["contest"]["environment_key"] == "geometry_world"
        assert context.json()["participant"]["external_ref"] == "geometry-flow-001"

        start_response = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert start_response.status_code == 200
        attempt = start_response.json()["attempt"]
        assert start_response.json()["created"] is True
        assert "seed" not in attempt

        with application.state.database.session_factory() as session:
            started_event = session.scalar(
                select(AttemptEvent).where(
                    AttemptEvent.attempt_id == attempt["id"],
                    AttemptEvent.event_type == "attempt_started",
                )
            )
            assert started_event is not None
            assert (
                started_event.payload["environment_key_snapshot"]
                == "geometry_world"
            )
            assert started_event.payload["task_config_snapshot"] == (
                contest["task_config"]
            )

        current_response = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        assert current_response.status_code == 200
        first = current_response.json()["task"]
        assert first["ordinal"] == 1
        assert first["family"] == "geo_transform"
        assert first["generator_version"] == GEOMETRY_GENERATOR_VERSION
        assert first["difficulty"] == 1
        assert first["public_state"]["kind"] == "geometry_atlas"
        assert first["public_state"]["family"] == "geo_transform"
        assert first["public_state"]["world_context"] == {
            "world": "geometry_world",
            "episode": 1,
            "family": "geo_transform",
            "phase": "calibration",
        }
        assert "private_state" not in first
        assert "seed" not in first

        same_current = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        )
        assert same_current.status_code == 200
        assert same_current.json() == {"task": first, "created": False}

        _answer_geometry_task(
            client,
            application,
            participant,
            first,
        )

        second_response = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        )
        assert second_response.status_code == 200
        assert second_response.json()["created"] is True
        second = second_response.json()["task"]
        assert second["ordinal"] == 2
        assert second["family"] == "geo_transform"

        skipped = client.post(
            f"/api/v1/participant/tasks/{second['id']}/skip",
            headers=auth(participant),
        )
        assert skipped.status_code == 200
        assert skipped.json()["task"]["status"] == "skipped"

        third_response = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        )
        assert third_response.status_code == 200
        third = third_response.json()["task"]
        assert third["ordinal"] == 3
        assert third["family"] == "geo_transform"
        # With a single enabled family there is nowhere else to rotate, but a
        # skip still opens a fresh regular task rather than remediation.
        assert third["public_state"]["world_context"]["phase"] == "rotation"

        with application.state.database.session_factory() as session:
            generated_events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(
                        AttemptEvent.attempt_id == attempt["id"],
                        AttemptEvent.event_type == "task_generated",
                    )
                    .order_by(AttemptEvent.sequence)
                )
            )
            assert len(generated_events) == 3
            assert all(
                event.payload["environment_key"] == "geometry_world"
                for event in generated_events
            )
            assert all(
                event.payload["director_version"] == GEOMETRY_DIRECTOR_VERSION
                for event in generated_events
            )


def test_geo_zendo_probe_updates_public_state_without_leaking_truths(tmp_path):
    application = create_app(_settings(tmp_path / "geometry-zendo-probe.db"))
    family = {
        "key": "geo_zendo",
        "enabled": True,
        "weight": 1,
        "initial_difficulty": 1,
        "max_difficulty": 4,
    }

    with TestClient(application) as client:
        participant, _contest, _code = _create_geometry_participant(
            client,
            external_ref="geometry-zendo-001",
            families=[family],
            start_family="geo_zendo",
        )
        start_response = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert start_response.status_code == 200

        current_response = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        assert current_response.status_code == 200
        task = current_response.json()["task"]
        assert task["family"] == "geo_zendo"
        assert (
            task["public_state"]["interaction"]["mode"]
            == "probe_then_answer"
        )
        assert _nested_keys(task).isdisjoint(GEOMETRY_PRIVATE_KEYS)

        initial_content = task["public_state"]["content"]
        probe_id = initial_content["probe_cards"][0]["card_id"]
        initial_remaining = initial_content["probes_remaining"]
        assert initial_remaining > 0
        assert initial_content["probe_observations"] == []

        probe_response = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "geometry-zendo-probe-1",
                "action_type": "probe",
                "probe": probe_id.lower(),
            },
        )
        assert probe_response.status_code == 200
        probe_result = probe_response.json()
        assert probe_result["accepted"] is True
        assert probe_result["completed"] is False
        assert probe_result["client_action_id"] == "geometry-zendo-probe-1"
        assert probe_result["task"]["status"] == "active"
        assert _nested_keys(probe_result["task"]).isdisjoint(
            GEOMETRY_PRIVATE_KEYS
        )

        updated_content = probe_result["task"]["public_state"]["content"]
        assert updated_content["probes_remaining"] == initial_remaining - 1
        assert len(updated_content["probe_observations"]) == 1
        observation = updated_content["probe_observations"][0]
        assert observation["card_id"] == probe_id
        assert observation["classification"] in {
            "positive",
            "negative",
        }
        assert next(
            item
            for item in updated_content["probe_cards"]
            if item["card_id"] == probe_id
        )["used"] is True

        answer_response = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={
                "answer": _correct_geometry_answer(application, task["id"])
            },
        )
        assert answer_response.status_code == 200
        assert answer_response.json()["task"]["status"] == "answered"
        assert _nested_keys(answer_response.json()["task"]).isdisjoint(
            GEOMETRY_PRIVATE_KEYS
        )

        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            assert stored.evaluation_state["correct"] is True
            assert stored.private_state["probes_remaining"] == (
                initial_remaining - 1
            )


def test_geometry_world_rejects_family_from_chess_world(tmp_path):
    application = create_app(_settings(tmp_path / "geometry-wrong-family.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        response = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Некорректный геометрический контест",
                "environment_key": "geometry_world",
                "task_config": _geometry_config(
                    families=[
                        {
                            "key": "dice_chess",
                            "enabled": True,
                            "weight": 1,
                            "initial_difficulty": 1,
                            "max_difficulty": 4,
                        }
                    ],
                    start_family="dice_chess",
                ),
            },
        )

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "TASK_FAMILY_WORLD_MISMATCH"


def _run_reproducible_geometry_route(
    database_path: Path,
) -> list[tuple[str, int, str]]:
    application = create_app(_settings(database_path))
    families = [
        {
            "key": "geo_transform",
            "enabled": True,
            "weight": 1,
            "initial_difficulty": 1,
            "max_difficulty": 4,
        },
        {
            "key": "geo_probability",
            "enabled": True,
            "weight": 1,
            "initial_difficulty": 1,
            "max_difficulty": 4,
        },
    ]

    with TestClient(application) as client:
        participant, _contest, _code = _create_geometry_participant(
            client,
            external_ref="geometry-route-001",
            families=families,
            start_family="geo_transform",
        )
        attempt = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        ).json()["attempt"]
        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            stored_attempt.seed = 867_530_9
            session.commit()

        route: list[tuple[str, int, str]] = []
        for ordinal in range(1, 9):
            if ordinal == 1:
                response = client.get(
                    "/api/v1/participant/tasks/current",
                    headers=auth(participant),
                )
            else:
                response = client.post(
                    "/api/v1/participant/tasks/next",
                    headers=auth(participant),
                )
            assert response.status_code == 200
            task = response.json()["task"]
            assert task["ordinal"] == ordinal
            assert task["public_state"]["kind"] == "geometry_atlas"
            assert (
                task["public_state"]["world_context"]["world"]
                == "geometry_world"
            )
            route.append(
                (
                    task["family"],
                    task["difficulty"],
                    task["public_state"]["world_context"]["phase"],
                )
            )
            _answer_geometry_task(
                client,
                application,
                participant,
                task,
            )

    return route


def test_geometry_world_adapts_after_strong_answers_and_route_is_reproducible(
    tmp_path,
):
    first_route = _run_reproducible_geometry_route(
        tmp_path / "geometry-route-first.db"
    )
    second_route = _run_reproducible_geometry_route(
        tmp_path / "geometry-route-second.db"
    )

    assert first_route == second_route
    assert first_route[0] == ("geo_transform", 1, "calibration")
    assert {family for family, _difficulty, _phase in first_route} == {
        "geo_transform",
        "geo_probability",
    }

    difficulties_by_family: dict[str, list[int]] = defaultdict(list)
    for family, difficulty, _phase in first_route:
        difficulties_by_family[family].append(difficulty)

    # Three strong answers at one level promote the next task of that family.
    assert difficulties_by_family["geo_transform"][:3] == [1, 1, 1]
    assert difficulties_by_family["geo_transform"][3] == 2
    assert difficulties_by_family["geo_probability"][:3] == [1, 1, 1]
    assert difficulties_by_family["geo_probability"][3] == 2
