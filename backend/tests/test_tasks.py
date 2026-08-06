from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.environments import (
    DICE_CHESS_FAMILY,
    DICE_CHESS_GENERATOR_VERSION,
    derive_task_seed,
    generate_task,
)
from app.main import create_app
from app.models import Attempt, AttemptEvent, AttemptStatus, TaskInstance, utc_now


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def _prepare_participant(client: TestClient) -> str:
    organizer = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    ).json()["access_token"]
    contest = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Dice & Chess",
            "task_config": {
                "adaptation_threshold": 3,
                "families": [
                    {
                        "key": "dice_chess",
                        "enabled": True,
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
                {"external_ref": "task-001", "display_name": "Участник"}
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
    return client.post(
        "/api/v1/access/redeem",
        json={"code": code},
    ).json()["access_token"]


def test_dice_chess_generator_is_deterministic_and_preserves_invariants():
    first_seed = derive_task_seed(
        attempt_seed=9_001,
        ordinal=7,
        family=DICE_CHESS_FAMILY,
        generator_version=DICE_CHESS_GENERATOR_VERSION,
    )
    assert first_seed == derive_task_seed(
        attempt_seed=9_001,
        ordinal=7,
        family=DICE_CHESS_FAMILY,
        generator_version=DICE_CHESS_GENERATOR_VERSION,
    )
    assert first_seed != derive_task_seed(
        attempt_seed=9_001,
        ordinal=8,
        family=DICE_CHESS_FAMILY,
        generator_version=DICE_CHESS_GENERATOR_VERSION,
    )
    assert first_seed != derive_task_seed(
        attempt_seed=9_001,
        ordinal=7,
        family=DICE_CHESS_FAMILY,
        generator_version="dice-chess-world-v2",
    )

    for source_seed in range(500):
        task_seed = derive_task_seed(
            attempt_seed=source_seed,
            ordinal=1,
            family=DICE_CHESS_FAMILY,
            generator_version=DICE_CHESS_GENERATOR_VERSION,
        )
        generated = generate_task(
            family=DICE_CHESS_FAMILY,
            generator_version=DICE_CHESS_GENERATOR_VERSION,
            seed=task_seed,
            difficulty=1,
        )
        repeated = generate_task(
            family=DICE_CHESS_FAMILY,
            generator_version=DICE_CHESS_GENERATOR_VERSION,
            seed=task_seed,
            difficulty=1,
        )
        assert generated == repeated

        public = generated.public_state
        assert public["kind"] == "dice_chess_board_inventory_probability"
        board = public["board"]
        assert len(board) == 8
        assert all(len(row) == 8 for row in board)
        assert len(public["die"]["faces"]) == 6
        probability = generated.private_state["probability"]
        assert 1 <= probability["numerator"] < probability["denominator"] <= 6
        assert (
            generated.private_state["favorable_faces"]
            * probability["denominator"]
            == probability["numerator"]
            * generated.private_state["total_faces"]
        )


def test_task_api_is_idempotent_and_does_not_leak_evaluation(tmp_path):
    application = create_app(_settings(tmp_path / "tasks.db"))
    with TestClient(application) as client:
        participant = _prepare_participant(client)

        without_attempt = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        assert without_attempt.status_code == 409
        assert without_attempt.json()["detail"]["code"] == "ACTIVE_ATTEMPT_REQUIRED"

        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert started.status_code == 200

        current = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        assert current.status_code == 200
        task = current.json()["task"]
        assert set(task) == {
            "id",
            "ordinal",
            "family",
            "generator_version",
            "difficulty",
            "status",
            "public_state",
            "created_at",
            "completed_at",
        }
        assert task["ordinal"] == 1
        assert task["family"] == "dice_chess"
        assert task["difficulty"] == 2
        assert task["status"] == "active"
        assert set(task["public_state"]) == {
            "kind",
            "prompt",
            "board",
            "die",
            "event_description",
            "sample_space_size",
            "response_hint",
        }
        assert task["public_state"]["kind"] == (
            "dice_chess_board_inventory_probability"
        )
        assert len(task["public_state"]["board"]) == 8

        same_current = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        assert same_current.json()["task"]["id"] == task["id"]

        no_implicit_skip = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        )
        assert no_implicit_skip.status_code == 200
        assert no_implicit_skip.json() == {"task": task, "created": False}

        with application.state.database.session_factory() as session:
            stored_before_answer = session.get(TaskInstance, task["id"])
            assert stored_before_answer is not None
            probability = stored_before_answer.private_state["probability"]
            correct_answer = (
                f"{probability['numerator']}/{probability['denominator']}"
            )
        answered = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": correct_answer},
        )
        assert answered.status_code == 200
        action = answered.json()
        assert set(action) == {"task", "message"}
        assert action["task"]["status"] == "answered"
        assert "correct" not in action
        assert "private_state" not in action["task"]
        assert "evaluation_state" not in action["task"]
        assert "participant_answer" not in action["task"]
        assert "seed" not in action["task"]

        repeated_same_answer = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": correct_answer},
        )
        assert repeated_same_answer.status_code == 200
        assert repeated_same_answer.json()["task"]["status"] == "answered"

        repeated_answer = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": f"{correct_answer} другой"},
        )
        assert repeated_answer.status_code == 409
        assert repeated_answer.json()["detail"]["code"] == "TASK_ALREADY_CLOSED"

        next_response = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        )
        assert next_response.status_code == 200
        assert next_response.json()["created"] is True
        next_task = next_response.json()["task"]
        assert next_task["ordinal"] == 2
        assert next_task["id"] != task["id"]

        skipped = client.post(
            f"/api/v1/participant/tasks/{next_task['id']}/skip",
            headers=auth(participant),
        )
        assert skipped.status_code == 200
        assert skipped.json()["task"]["status"] == "skipped"
        assert set(skipped.json()) == {"task", "message"}

        repeated_skip = client.post(
            f"/api/v1/participant/tasks/{next_task['id']}/skip",
            headers=auth(participant),
        )
        assert repeated_skip.status_code == 200
        assert repeated_skip.json()["task"]["status"] == "skipped"

        with application.state.database.session_factory() as session:
            stored_tasks = list(
                session.scalars(
                    select(TaskInstance).order_by(TaskInstance.ordinal)
                ).all()
            )
            assert (
                stored_tasks[0].private_state["mission_variant"]
                == "board_inventory_probability"
            )
            assert stored_tasks[0].evaluation_state["correct"] is True
            assert stored_tasks[0].participant_answer
            assert stored_tasks[1].evaluation_state["skipped"] is True
            assert (
                stored_tasks[1].evaluation_state["director_signal"]
                == "struggle"
            )

            events = list(
                session.scalars(
                    select(AttemptEvent).order_by(
                        AttemptEvent.sequence,
                    )
                ).all()
            )
            assert [event.event_type for event in events] == [
                "attempt_started",
                "task_generated",
                "answer_submitted",
                "answer_evaluated",
                "task_generated",
                "task_skipped",
            ]
            assert [event.sequence for event in events] == [1, 2, 3, 4, 5, 6]
            assert events[2].payload["answer"]
            assert events[3].payload["correct"] is True


def test_contest_with_retired_family_is_rejected(tmp_path):
    application = create_app(_settings(tmp_path / "retired.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        for retired_key in ("chess960", "chess_960", "penultima", "nim_like", "geo_graph"):
            rejected = client.post(
                "/api/v1/contests",
                headers=auth(organizer),
                json={
                    "title": "Retired",
                    "task_config": {"families": [retired_key]},
                },
            )
            assert rejected.status_code == 422, retired_key
            detail = rejected.json()["detail"]
            assert detail["code"] == "TASK_FAMILY_UNKNOWN"
            assert retired_key in detail["message"]


def test_expired_attempt_cannot_generate_or_submit_tasks(tmp_path):
    application = create_app(_settings(tmp_path / "deadline.db"))
    with TestClient(application) as client:
        participant = _prepare_participant(client)
        client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        task = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        ).json()["task"]

        with application.state.database.session_factory() as session:
            attempt = session.scalar(select(Attempt))
            assert attempt is not None
            attempt.deadline_at = utc_now() - timedelta(seconds=1)
            session.commit()

        rejected = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": "1/2"},
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"]["code"] == "ACTIVE_ATTEMPT_REQUIRED"

        rejected_next = client.post(
            "/api/v1/participant/tasks/next",
            headers=auth(participant),
        )
        assert rejected_next.status_code == 409

        with application.state.database.session_factory() as session:
            attempt = session.scalar(select(Attempt))
            assert attempt is not None
            assert attempt.status == AttemptStatus.EXPIRED
            events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.attempt_id == attempt.id)
                    .order_by(AttemptEvent.sequence)
                ).all()
            )
            assert events[-1].event_type == "attempt_expired"
