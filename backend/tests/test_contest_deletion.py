from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import (
    AccessCode,
    Attempt,
    AttemptEvent,
    AttemptGrant,
    Contest,
    Enrollment,
    Participant,
    TaskInstance,
    TaskInteraction,
    utc_now,
)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def _organizer_token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "organizer"
    return response.json()["access_token"]


def _geometry_config() -> dict:
    return {
        "adaptation_threshold": 3,
        "trajectory": {
            "mode": "adaptive",
            "director_version": "geometry-world-director-v1",
            "start_family": "geo_zendo",
        },
        "families": [
            {
                "key": "geo_zendo",
                "enabled": True,
                "weight": 1,
                "initial_difficulty": 1,
                "max_difficulty": 4,
            }
        ],
    }


def _create_contest_with_participant(
    client: TestClient,
    organizer: str,
    *,
    external_ref: str,
    publish: bool,
) -> dict:
    contest_response = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": f"Контест {external_ref}",
            "duration_minutes": 60,
            "environment_key": "geometry_world",
            "task_config": _geometry_config(),
        },
    )
    assert contest_response.status_code == 201
    contest = contest_response.json()

    enrollment_response = client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {
                    "external_ref": external_ref,
                    "display_name": f"Участник {external_ref}",
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
    assert code_response.json()["generated_count"] == 1
    participant_code = code_response.json()["items"][0]["code"]

    participant_token = None
    if publish:
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
        participant_token = redeem_response.json()["access_token"]

    return {
        "contest": contest,
        "enrollment": enrollment,
        "participant_code": participant_code,
        "participant_token": participant_token,
    }


def _row_count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _assert_only_global_participant_remains(
    application,
    *,
    participant_id: str,
    external_ref: str,
) -> None:
    with application.state.database.session_factory() as session:
        assert _row_count(session, Contest) == 0
        assert _row_count(session, Enrollment) == 0
        assert _row_count(session, AccessCode) == 0
        assert _row_count(session, Attempt) == 0
        assert _row_count(session, AttemptGrant) == 0
        assert _row_count(session, TaskInstance) == 0
        assert _row_count(session, TaskInteraction) == 0
        assert _row_count(session, AttemptEvent) == 0

        assert _row_count(session, Participant) == 1
        participant = session.get(Participant, participant_id)
        assert participant is not None
        assert participant.external_ref == external_ref


def test_delete_contest_requires_organizer(tmp_path):
    application = create_app(_settings(tmp_path / "delete-role.db"))
    with TestClient(application) as client:
        organizer = _organizer_token(client)
        created = _create_contest_with_participant(
            client,
            organizer,
            external_ref="delete-role-001",
            publish=True,
        )
        contest_id = created["contest"]["id"]
        participant = created["participant_token"]
        assert participant is not None

        anonymous = client.delete(f"/api/v1/contests/{contest_id}")
        assert anonymous.status_code == 401

        forbidden = client.delete(
            f"/api/v1/contests/{contest_id}",
            headers=auth(participant),
        )
        assert forbidden.status_code == 403

        listed = client.get(
            "/api/v1/contests",
            headers=auth(organizer),
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [contest_id]


def test_delete_contest_returns_404_for_unknown_id(tmp_path):
    application = create_app(_settings(tmp_path / "delete-missing.db"))
    with TestClient(application) as client:
        organizer = _organizer_token(client)
        response = client.delete(
            "/api/v1/contests/00000000-0000-0000-0000-000000000000",
            headers=auth(organizer),
        )

        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "CONTEST_NOT_FOUND"


def test_delete_draft_contest_cascades_enrollment_code_and_grant(tmp_path):
    application = create_app(_settings(tmp_path / "delete-draft.db"))
    external_ref = "delete-draft-001"
    with TestClient(application) as client:
        organizer = _organizer_token(client)
        created = _create_contest_with_participant(
            client,
            organizer,
            external_ref=external_ref,
            publish=False,
        )
        contest_id = created["contest"]["id"]
        enrollment = created["enrollment"]
        participant_id = enrollment["participant_id"]

        grant_response = client.post(
            (
                f"/api/v1/contests/{contest_id}/enrollments/"
                f"{enrollment['id']}/attempts/grant"
            ),
            headers=auth(organizer),
        )
        assert grant_response.status_code == 200
        assert grant_response.json()["pending"] is True

        with application.state.database.session_factory() as session:
            assert _row_count(session, Contest) == 1
            assert _row_count(session, Participant) == 1
            assert _row_count(session, Enrollment) == 1
            assert _row_count(session, AccessCode) == 1
            assert _row_count(session, AttemptGrant) == 1

        deleted = client.delete(
            f"/api/v1/contests/{contest_id}",
            headers=auth(organizer),
        )
        assert deleted.status_code == 204
        assert deleted.content == b""

        _assert_only_global_participant_remains(
            application,
            participant_id=participant_id,
            external_ref=external_ref,
        )


def test_delete_published_contest_cascades_full_attempt_graph(tmp_path):
    application = create_app(_settings(tmp_path / "delete-published.db"))
    external_ref = "delete-published-001"
    with TestClient(application) as client:
        organizer = _organizer_token(client)
        created = _create_contest_with_participant(
            client,
            organizer,
            external_ref=external_ref,
            publish=True,
        )
        contest_id = created["contest"]["id"]
        enrollment = created["enrollment"]
        participant_id = enrollment["participant_id"]
        participant = created["participant_token"]
        assert participant is not None

        start_response = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert start_response.status_code == 200
        attempt = start_response.json()["attempt"]

        current_response = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        assert current_response.status_code == 200
        task = current_response.json()["task"]
        assert task["family"] == "geo_zendo"
        probe_id = task["public_state"]["content"]["probe_cards"][0]["card_id"]

        interaction_response = client.post(
            f"/api/v1/participant/tasks/{task['id']}/interactions",
            headers=auth(participant),
            json={
                "client_action_id": "delete-cascade-probe-1",
                "action_type": "probe",
                "probe": probe_id,
            },
        )
        assert interaction_response.status_code == 200
        assert interaction_response.json()["accepted"] is True

        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            stored_attempt.deadline_at = utc_now() - timedelta(seconds=1)
            session.commit()

        grant_response = client.post(
            (
                f"/api/v1/contests/{contest_id}/enrollments/"
                f"{enrollment['id']}/attempts/grant"
            ),
            headers=auth(organizer),
        )
        assert grant_response.status_code == 200
        assert grant_response.json()["pending"] is True

        with application.state.database.session_factory() as session:
            assert _row_count(session, Contest) == 1
            assert _row_count(session, Participant) == 1
            assert _row_count(session, Enrollment) == 1
            assert _row_count(session, AccessCode) == 1
            assert _row_count(session, Attempt) == 1
            assert _row_count(session, AttemptGrant) == 1
            assert _row_count(session, TaskInstance) == 1
            assert _row_count(session, TaskInteraction) == 1
            assert _row_count(session, AttemptEvent) >= 5

        deleted = client.delete(
            f"/api/v1/contests/{contest_id}",
            headers=auth(organizer),
        )
        assert deleted.status_code == 204
        assert deleted.content == b""

        _assert_only_global_participant_remains(
            application,
            participant_id=participant_id,
            external_ref=external_ref,
        )
