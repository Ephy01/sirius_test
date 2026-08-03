"""Organizer debug mode: the /get answer command reveals reference answers."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import AttemptEvent, TaskInstance


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def _prepare_participant(client, *, task_config: dict) -> tuple[str, str]:
    organizer = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    ).json()["access_token"]
    contest = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={"title": "Debug answers", "task_config": task_config},
    ).json()
    client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {"external_ref": "debug-001", "display_name": "Отладчик"}
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


def test_debug_answer_solves_task_and_logs_event(tmp_path):
    application = create_app(_settings(tmp_path / "debug-on.db"))
    with TestClient(application) as client:
        participant, _contest_id = _prepare_participant(
            client,
            task_config={
                "debug_reveal_answers": True,
                "families": [
                    {
                        "family": "token_zendo",
                        "weight": 1,
                        "initial_difficulty": 2,
                        "max_difficulty": 5,
                    }
                ],
            },
        )
        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]

        revealed = client.get(
            f"/api/v1/participant/tasks/{task['id']}/debug-answer",
            headers=auth(participant),
        )
        assert revealed.status_code == 200, revealed.text
        payload = revealed.json()
        assert payload["family"] == "token_zendo"
        assert payload["answer"].startswith("/answer ")
        assert payload["commands"] == []

        answered = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": payload["answer"]},
        )
        assert answered.status_code == 200
        with application.state.database.session_factory() as session:
            stored = session.get(TaskInstance, task["id"])
            assert stored.evaluation_state["correct"] is True
            events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "debug_answer_revealed"
                    )
                )
            )
            assert len(events) == 1
            assert events[0].payload["family"] == "token_zendo"


def test_debug_answer_returns_commands_for_interactive_families(tmp_path):
    application = create_app(_settings(tmp_path / "debug-wiring.db"))
    with TestClient(application) as client:
        participant, _contest_id = _prepare_participant(
            client,
            task_config={
                "debug_reveal_answers": True,
                "families": [
                    {
                        "family": "hidden_wiring",
                        "weight": 1,
                        "initial_difficulty": 1,
                        "max_difficulty": 2,
                    }
                ],
            },
        )
        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]
        assert task["public_state"]["variant"] == "reach_target"

        revealed = client.get(
            f"/api/v1/participant/tasks/{task['id']}/debug-answer",
            headers=auth(participant),
        ).json()
        assert revealed["commands"]
        assert all(
            command.startswith("/op ")
            for command in revealed["commands"]
        )

        current = task
        for index, command in enumerate(revealed["commands"]):
            response = client.post(
                f"/api/v1/participant/tasks/{task['id']}/interactions",
                headers=auth(participant),
                json={
                    "client_action_id": f"debug-chord-{index}",
                    "action_type": "apply_op",
                    "op_id": command.removeprefix("/op "),
                },
            )
            assert response.status_code == 200
            current = response.json()["task"]
        assert current["status"] == "answered"


def test_debug_answer_is_forbidden_without_the_toggle(tmp_path):
    application = create_app(_settings(tmp_path / "debug-off.db"))
    with TestClient(application) as client:
        participant, _contest_id = _prepare_participant(
            client,
            task_config={
                "families": [
                    {
                        "family": "token_zendo",
                        "weight": 1,
                        "initial_difficulty": 1,
                        "max_difficulty": 5,
                    }
                ],
            },
        )
        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]

        forbidden = client.get(
            f"/api/v1/participant/tasks/{task['id']}/debug-answer",
            headers=auth(participant),
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"]["code"] == "DEBUG_ANSWERS_DISABLED"
