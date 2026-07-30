from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.environments import (
    CHESS960_FAMILY,
    CHESS960_GENERATOR_VERSION,
    derive_task_seed,
    generate_task,
)
from app.environments.chess_world.chess960 import (
    chess960_violations,
    is_valid_chess960,
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
            "title": "Chess960",
            "task_config": {
                "adaptation_threshold": 3,
                "families": [
                    {
                        "key": "chess960",
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


def test_chess960_generator_is_deterministic_and_preserves_invariants():
    first_seed = derive_task_seed(
        attempt_seed=9_001,
        ordinal=7,
        family=CHESS960_FAMILY,
        generator_version=CHESS960_GENERATOR_VERSION,
    )
    assert first_seed == derive_task_seed(
        attempt_seed=9_001,
        ordinal=7,
        family=CHESS960_FAMILY,
        generator_version=CHESS960_GENERATOR_VERSION,
    )
    assert first_seed != derive_task_seed(
        attempt_seed=9_001,
        ordinal=8,
        family=CHESS960_FAMILY,
        generator_version=CHESS960_GENERATOR_VERSION,
    )
    assert first_seed != derive_task_seed(
        attempt_seed=9_001,
        ordinal=7,
        family=CHESS960_FAMILY,
        generator_version="chess960-validation-v2",
    )

    for source_seed in range(500):
        task_seed = derive_task_seed(
            attempt_seed=source_seed,
            ordinal=1,
            family=CHESS960_FAMILY,
            generator_version=CHESS960_GENERATOR_VERSION,
        )
        generated = generate_task(
            family=CHESS960_FAMILY,
            generator_version=CHESS960_GENERATOR_VERSION,
            seed=task_seed,
            difficulty=1,
        )
        repeated = generate_task(
            family=CHESS960_FAMILY,
            generator_version=CHESS960_GENERATOR_VERSION,
            seed=task_seed,
            difficulty=1,
        )
        assert generated == repeated

        back_rank = generated.public_state["back_rank"]
        assert len(back_rank) == 8
        assert generated.public_state["kind"] == "chess960_mission"
        assert generated.public_state["variant"] == "validation"
        violations = chess960_violations(back_rank)
        if generated.private_state["is_valid"]:
            assert is_valid_chess960(back_rank)
            assert violations == set()
            assert generated.private_state["violation"] is None
        else:
            assert not is_valid_chess960(back_rank)
            assert violations == {generated.private_state["violation"]}


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
        assert task["family"] == "chess960"
        assert task["difficulty"] == 2
        assert task["status"] == "active"
        assert set(task["public_state"]) == {
            "kind",
            "variant",
            "prompt",
            "back_rank",
            "response_hint",
        }
        assert task["public_state"]["kind"] == "chess960_mission"
        assert task["public_state"]["variant"] == "single_swap_repair"
        assert len(task["public_state"]["back_rank"]) == 8

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
            first_repair = stored_before_answer.private_state["valid_repairs"][0]
            correct_answer = f"{first_repair[0]} {first_repair[1]}"
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

        repeated_answer = client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": "Да"},
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

        with application.state.database.session_factory() as session:
            stored_tasks = list(
                session.scalars(
                    select(TaskInstance).order_by(TaskInstance.ordinal)
                ).all()
            )
            assert stored_tasks[0].private_state["variant"] == "single_swap_repair"
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
            json={"answer": "Да"},
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
