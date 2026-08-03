"""End-to-end smoke: the §7 default contest covers every family."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.environments import IMPLEMENTED_FAMILIES
from app.main import create_app
from app.models import Attempt, TaskInstance

# Coverage weights of the default contest config (ТЗ v3 §7).
DEFAULT_FAMILIES = [
    ("geo_zendo", 14),
    ("token_zendo", 12),
    ("point_zendo", 12),
    ("grid_zendo", 12),
    ("hidden_wiring", 14),
    ("machine_reach", 12),
    ("fold_punch", 8),
    ("dice_chess", 6),
    ("geo_transform", 2),
    ("geo_probability", 2),
]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def _solve_task(client, application, participant, task) -> None:
    family = task["family"]
    with application.state.database.session_factory() as session:
        stored = session.get(TaskInstance, task["id"])
        assert stored is not None
        private = dict(stored.private_state)

    if family in {"geo_zendo", "token_zendo", "point_zendo", "grid_zendo"}:
        answer = " ".join(
            "да" if value else "нет"
            for value in private["target_answers"]
        )
    elif family == "hidden_wiring":
        if private["variant"] == "reach_target":
            for index, chord in enumerate(private["certificate"]):
                response = client.post(
                    f"/api/v1/participant/tasks/{task['id']}/interactions",
                    headers=auth(participant),
                    json={
                        "client_action_id": f"{task['id']}-chord-{index}",
                        "action_type": "apply_op",
                        "op_id": chord,
                    },
                )
                assert response.status_code == 200, response.text
                assert response.json()["accepted"] is True
            assert response.json()["task"]["status"] == "answered"
            return
        lamp_count = int(private["lamp_count"])
        answer = " ".join(
            "".join(
                "1" if (effect >> index) & 1 else "0"
                for index in range(lamp_count)
            )
            for effect in private["exam_effects"]
        )
    elif family == "machine_reach":
        if private.get("reachable"):
            for index, op_id in enumerate(private["witness"]):
                response = client.post(
                    f"/api/v1/participant/tasks/{task['id']}/interactions",
                    headers=auth(participant),
                    json={
                        "client_action_id": f"{task['id']}-op-{index}",
                        "action_type": "apply_op",
                        "op_id": op_id,
                    },
                )
                assert response.status_code == 200, response.text
            answer = "done"
        else:
            answer = "impossible"
    elif family == "fold_punch":
        answer = " ".join(
            f"{row + 1},{column + 1}"
            for row, column in private["expected_holes"]
        )
    elif family in {"dice_chess", "geo_probability"}:
        probability = private["probability"]
        answer = f"{probability['numerator']}/{probability['denominator']}"
    elif family == "geo_transform":
        answer = str(private["correct_card_id"])
    else:  # pragma: no cover - защита от появления неизвестного семейства
        raise AssertionError(f"No oracle for family {family!r}")

    answered = client.post(
        f"/api/v1/participant/tasks/{task['id']}/answer",
        headers=auth(participant),
        json={"answer": answer},
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["task"]["status"] == "answered"


def test_default_contest_covers_every_family_end_to_end(tmp_path):
    application = create_app(_settings(tmp_path / "default-smoke.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Отбор: контент v3",
                "duration_minutes": 120,
                "environment_key": "mixed",
                "task_config": {
                    "adaptation_threshold": 3,
                    "trajectory": {
                        "mode": "adaptive",
                        "start_family": "geo_zendo",
                    },
                    "families": [
                        {
                            "family": family,
                            "weight": weight,
                            "initial_difficulty": 1,
                            "max_difficulty": 5,
                            **(
                                {
                                    "sub_kinds": [
                                        "lamps_gf2",
                                        "numeric_machine",
                                        "perm_puzzle",
                                        "leaper_board",
                                    ]
                                }
                                if family == "machine_reach"
                                else {}
                            ),
                        }
                        for family, weight in DEFAULT_FAMILIES
                    ],
                },
            },
        )
        assert contest.status_code == 201, contest.text
        contest = contest.json()
        client.post(
            f"/api/v1/contests/{contest['id']}/enrollments",
            headers=auth(organizer),
            json={
                "participants": [
                    {"external_ref": "smoke-001", "display_name": "Смоук"}
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

        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        ).json()["attempt"]
        with application.state.database.session_factory() as session:
            attempt = session.get(Attempt, started["id"])
            attempt.seed = 20_260_731
            session.commit()

        seen_families: set[str] = set()
        expected = {family for family, _weight in DEFAULT_FAMILIES}
        assert expected <= IMPLEMENTED_FAMILIES
        for ordinal in range(1, 31):
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
            assert request.status_code == 200, request.text
            task = request.json()["task"]
            seen_families.add(task["family"])
            _solve_task(client, application, participant, task)
            if seen_families == expected:
                break
        assert seen_families == expected, (
            f"families not covered after 30 tasks: {expected - seen_families}"
        )

        # Every family produced a scored, answered task instance.
        with application.state.database.session_factory() as session:
            tasks = list(session.scalars(select(TaskInstance)).all())
            for stored in tasks:
                assert stored.status.value in {"answered", "skipped"} or (
                    stored.active_slot is True
                )
                if stored.evaluation_state:
                    evaluation = stored.evaluation_state
                    assert evaluation["family"] == stored.family
                    assert 0.0 <= evaluation["continuous_score"] <= 1.0
