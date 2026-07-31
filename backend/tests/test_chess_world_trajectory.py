from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import Attempt, AttemptEvent, Contest, TaskInstance


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def _prepare_participant(
    client: TestClient,
    *,
    families: list[dict],
    start_family: str,
    director_version: str | None = "chess-world-director-v1",
) -> tuple[str, str]:
    organizer = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    ).json()["access_token"]
    trajectory: dict = {
        "mode": "adaptive",
        "start_family": start_family,
    }
    if director_version is not None:
        trajectory["director_version"] = director_version
    contest = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Adaptive Chess World",
            "task_config": {
                "adaptation_threshold": 3,
                "trajectory": trajectory,
                "families": families,
            },
        },
    ).json()
    client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {
                    "external_ref": f"trajectory-{contest['id']}",
                    "display_name": "Участник",
                }
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
    return participant, contest["id"]


def _fix_attempt_seed(application, attempt_id: str, seed: int = 424_242) -> None:
    with application.state.database.session_factory() as session:
        attempt = session.get(Attempt, attempt_id)
        assert attempt is not None
        attempt.seed = seed
        session.commit()


def _correct_answer(application, task_id: str) -> str:
    with application.state.database.session_factory() as session:
        task = session.get(TaskInstance, task_id)
        assert task is not None
        private = task.private_state
        if task.family == "dice_chess":
            probability = private["probability"]
            return f"{probability['numerator']}/{probability['denominator']}"
    raise AssertionError(f"No oracle for family {task.family!r}")


def _answer_correctly(
    client: TestClient,
    application,
    participant: str,
    task: dict,
) -> None:
    response = client.post(
        f"/api/v1/participant/tasks/{task['id']}/answer",
        headers=auth(participant),
        json={"answer": _correct_answer(application, task["id"])},
    )
    assert response.status_code == 200


def test_adaptive_route_uses_snapshot_and_promotes_one_family(tmp_path):
    application = create_app(_settings(tmp_path / "adaptive-level.db"))
    families = [
        {
            "key": "dice_chess",
            "enabled": True,
            "weight": 1,
            "initial_difficulty": 2,
            "max_difficulty": 5,
        }
    ]
    with TestClient(application) as client:
        participant, contest_id = _prepare_participant(
            client,
            families=families,
            start_family="dice_chess",
        )
        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        ).json()["attempt"]
        _fix_attempt_seed(application, started["id"])

        observed: list[dict] = []
        for ordinal in range(1, 4):
            endpoint = (
                "/api/v1/participant/tasks/current"
                if ordinal == 1
                else "/api/v1/participant/tasks/next"
            )
            request = (
                client.get(endpoint, headers=auth(participant))
                if ordinal == 1
                else client.post(endpoint, headers=auth(participant))
            )
            task = request.json()["task"]
            observed.append(task)
            assert task["family"] == "dice_chess"
            assert task["difficulty"] == 2
            assert task["public_state"]["world_context"]["episode"] == ordinal
            _answer_correctly(client, application, participant, task)

        with application.state.database.session_factory() as session:
            contest = session.get(Contest, contest_id)
            assert contest is not None
            contest.task_config = {
                "families": [
                    {
                        "key": "dice_chess",
                        "enabled": True,
                        "weight": 1,
                        "initial_difficulty": 1,
                        "max_difficulty": 1,
                    }
                ]
            }
            session.commit()

        promoted = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        assert promoted["difficulty"] == 3
        assert promoted["public_state"]["kind"] == "dice_chess_position_probability"

        with application.state.database.session_factory() as session:
            events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.attempt_id == started["id"])
                    .order_by(AttemptEvent.sequence)
                ).all()
            )
            started_event = events[0]
            assert started_event.payload["task_config_snapshot"]["trajectory"][
                "mode"
            ] == "adaptive"
            generated = [
                event for event in events if event.event_type == "task_generated"
            ]
            assert generated[0].payload["decision_reason"] == "configured_start_family"
            assert all(
                event.payload["director_version"] == "chess-world-director-v1"
                for event in generated
            )


def test_failure_gets_one_related_remediation_then_switches_family(tmp_path):
    application = create_app(_settings(tmp_path / "adaptive-remediation.db"))
    families = [
        {
            "key": "dice_chess",
            "enabled": True,
            "weight": 1,
            "initial_difficulty": 1,
            "max_difficulty": 5,
        },
        {
            "key": "machine_reach",
            "enabled": True,
            "weight": 1,
            "initial_difficulty": 1,
            "max_difficulty": 5,
        },
    ]
    with TestClient(application) as client:
        participant, _contest_id = _prepare_participant(
            client,
            families=families,
            start_family="dice_chess",
            director_version=None,
        )
        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        ).json()["attempt"]
        _fix_attempt_seed(application, started["id"])

        failed = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        assert failed["family"] == "dice_chess"
        correct = _correct_answer(application, failed["id"])
        wrong = client.post(
            f"/api/v1/participant/tasks/{failed['id']}/answer",
            headers=auth(participant),
            json={"answer": "1/6" if correct != "1/6" else "5/6"},
        )
        assert wrong.status_code == 200

        remediation = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        assert remediation["family"] == failed["family"]
        assert remediation["public_state"]["world_context"]["phase"] == "remediation"
        client.post(
            f"/api/v1/participant/tasks/{remediation['id']}/skip",
            headers=auth(participant),
        )

        switched = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        ).json()["task"]
        assert switched["family"] != remediation["family"]
        # The second family has not been calibrated yet, so leaving the
        # capped remediation lands on its seeded calibration task.
        assert switched["family"] == "machine_reach"
        assert switched["public_state"]["world_context"]["phase"] == "calibration"
