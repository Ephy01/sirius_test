"""Stage C: learning-slope quota/export and the paid /hint interaction."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.environments.director import (
    CompletedTask,
    DirectorPhase,
    FamilySettings,
    decide_next_task,
)
from app.main import create_app
from app.models import AttemptEvent, TaskInstance
from app.telemetry import _learning_slopes


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def test_soft_exposure_quota_prefers_families_below_three_shows() -> None:
    families = (
        FamilySettings(family="dice_chess", weight=100),
        FamilySettings(family="machine_reach", weight=1),
        FamilySettings(family="geo_transform", weight=1),
    )
    history = [
        CompletedTask(
            task_id=f"dice-{index}",
            family="dice_chess",
            difficulty=1,
            evidence=1,
            phase=(
                DirectorPhase.CALIBRATION
                if index == 0
                else DirectorPhase.ROTATION
            ),
        )
        for index in range(3)
    ] + [
        CompletedTask(
            task_id="machine-0",
            family="machine_reach",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.CALIBRATION,
        ),
    ] + [
        CompletedTask(
            task_id=f"geo-{index}",
            family="geo_transform",
            difficulty=1,
            evidence=1,
            phase=(
                DirectorPhase.CALIBRATION
                if index == 0
                else DirectorPhase.ROTATION
            ),
        )
        for index in range(3)
    ]

    without_quota = decide_next_task(
        seed=7,
        families=families,
        history=history,
    )
    assert without_quota.family == "dice_chess"
    assert without_quota.reason == "weighted_coverage_debt"

    with_quota = decide_next_task(
        seed=7,
        families=families,
        history=history,
        min_family_exposures=3,
    )
    assert with_quota.family == "machine_reach"
    assert with_quota.reason == "soft_exposure_quota"

    saturated_history = history + [
        CompletedTask(
            task_id=f"machine-{index}",
            family="machine_reach",
            difficulty=1,
            evidence=1,
            phase=DirectorPhase.ROTATION,
        )
        for index in range(1, 3)
    ]
    saturated = decide_next_task(
        seed=7,
        families=families,
        history=saturated_history,
        min_family_exposures=3,
    )
    assert saturated.family == "dice_chess"
    assert saturated.reason == "weighted_coverage_debt"


def test_learning_slope_formula() -> None:
    class _Task:
        def __init__(self, family, score):
            self.family = family
            self.evaluation_state = {"continuous_score": score}

    slopes = dict(
        _learning_slopes(
            [
                _Task("a", 0.0),
                _Task("a", 0.5),
                _Task("a", 1.0),
                _Task("b", 0.4),
            ]
        )
    )
    assert abs(slopes["a"] - 0.5) < 1e-9
    assert slopes["b"] is None


def test_hint_api_flow_logs_prompt_used_and_scales_score(tmp_path):
    application = create_app(_settings(tmp_path / "hint-api.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Hint Zendo",
                "task_config": {
                    "families": [
                        {
                            "family": "token_zendo",
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
                    {"external_ref": "hint-001", "display_name": "Участник"}
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

        hinted = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "hint-1",
                "action_type": "hint",
            },
        )
        assert hinted.status_code == 200
        assert hinted.json()["accepted"] is True
        assert "Подсказка" in hinted.json()["message"]
        assert "hint" in hinted.json()["task"]["public_state"]

        second = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "hint-2",
                "action_type": "hint",
            },
        )
        assert second.status_code == 200
        assert second.json()["accepted"] is False
        replay = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "hint-1",
                "action_type": "hint",
            },
        )
        assert replay.status_code == 200

        with application.state.database.session_factory() as session:
            prompt_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "prompt_used"
                    )
                )
            )
            assert len(prompt_events) == 1
            payload = prompt_events[0].payload
            assert payload["family"] == "token_zendo"
            assert payload["score_multiplier"] == 0.7
            assert payload["hint_category"]

            stored = session.get(TaskInstance, task["id"])
            assert stored is not None
            assert stored.private_state["hint_used"] is True
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
            assert evaluation["hint_used"] is True
            assert abs(evaluation["continuous_score"] - 0.7) < 1e-9


def test_learning_slope_appears_in_telemetry_export(tmp_path):
    application = create_app(_settings(tmp_path / "slope-export.db"))
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Slope Export",
                "task_config": {"families": ["dice_chess"]},
            },
        ).json()
        enrollment = client.post(
            f"/api/v1/contests/{contest['id']}/enrollments",
            headers=auth(organizer),
            json={
                "participants": [
                    {"external_ref": "slope-001", "display_name": "Участник"}
                ]
            },
        ).json()["items"][0]
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

        for ordinal in range(2):
            endpoint = (
                "/api/v1/participant/tasks/current"
                if ordinal == 0
                else "/api/v1/participant/tasks/next"
            )
            request = (
                client.get(endpoint, headers=auth(participant))
                if ordinal == 0
                else client.post(endpoint, headers=auth(participant))
            )
            task = request.json()["task"]
            with application.state.database.session_factory() as session:
                stored = session.get(TaskInstance, task["id"])
                probability = stored.private_state["probability"]
                answer = (
                    f"{probability['numerator']}/{probability['denominator']}"
                )
            client.post(
                f"/api/v1/participant/tasks/{task['id']}/answer",
                headers=auth(participant),
                json={"answer": answer},
            )

        export = client.get(
            f"/api/v1/contests/{contest['id']}"
            f"/enrollments/{enrollment['id']}/telemetry",
            headers=auth(organizer),
        )
        assert export.status_code == 200
        assert "--- LEARNING SLOPES ---" in export.text
        assert "learning_slope dice_chess: " in export.text
        slope_line = next(
            line
            for line in export.text.splitlines()
            if line.startswith("learning_slope dice_chess:")
        )
        assert slope_line.split(": ")[1] != ""
