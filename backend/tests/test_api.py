import re
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import AccessCode, AccessCodeStatus, utc_now


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def organizer_token(client: TestClient) -> str:
    response = client.post("/api/v1/access/redeem", json={"code": "ORBIT-ADMIN"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "organizer"
    return payload["access_token"]


def test_complete_contest_access_and_attempt_flow(tmp_path):
    database_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )

    with TestClient(create_app(settings)) as client:
        health = client.get("/api/v1/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        assert client.get("/api/v1/contests").status_code == 401
        organizer = organizer_token(client)

        created = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Шахматный мир",
                "duration_minutes": 60,
                "environment_key": "chess_world",
                "task_config": {
                    "families": ["dice_chess", "chess_960", "penultima"]
                },
            },
        )
        assert created.status_code == 201
        contest = created.json()
        assert contest["status"] == "draft"
        contest_id = contest["id"]

        listed = client.get("/api/v1/contests", headers=auth(organizer))
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()["items"]] == [contest_id]

        enrolled = client.post(
            f"/api/v1/contests/{contest_id}/enrollments",
            headers=auth(organizer),
            json={
                "participants": [
                    {"external_ref": "application-001", "display_name": "Иван Иванов"},
                    {"external_ref": "application-002", "display_name": "Анна Петрова"},
                ]
            },
        )
        assert enrolled.status_code == 201
        assert enrolled.json()["created_count"] == 2

        generated = client.post(
            f"/api/v1/contests/{contest_id}/codes",
            headers=auth(organizer),
            json={},
        )
        assert generated.status_code == 200
        generated_payload = generated.json()
        assert generated_payload["generated_count"] == 2
        assert generated_payload["skipped_count"] == 0
        participant_code = generated_payload["items"][0]["code"]
        assert re.fullmatch(r"SG-[A-HJ-KM-NP-Z2-9]{4}-[A-HJ-KM-NP-Z2-9]{4}", participant_code)

        unavailable = client.post(
            "/api/v1/access/redeem",
            json={"code": participant_code},
        )
        assert unavailable.status_code == 403
        assert unavailable.json()["detail"]["code"] == "CONTEST_NOT_PUBLISHED"

        published = client.post(
            f"/api/v1/contests/{contest_id}/publish",
            headers=auth(organizer),
        )
        assert published.status_code == 200
        assert published.json()["status"] == "published"

        redeemed = client.post("/api/v1/access/redeem", json={"code": participant_code})
        assert redeemed.status_code == 200
        assert redeemed.json()["role"] == "participant"
        participant = redeemed.json()["access_token"]

        forbidden = client.get("/api/v1/contests", headers=auth(participant))
        assert forbidden.status_code == 403

        context = client.get("/api/v1/participant/context", headers=auth(participant))
        assert context.status_code == 200
        context_payload = context.json()
        assert context_payload["contest"]["id"] == contest_id
        assert context_payload["participant"]["external_ref"] == "application-001"
        assert context_payload["active_attempt"] is None

        first_start = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert first_start.status_code == 200
        assert first_start.json()["created"] is True
        attempt = first_start.json()["attempt"]
        assert attempt["number"] == 1
        assert attempt["status"] == "active"
        assert attempt["seed"] > 0
        assert attempt["deadline_at"].endswith("Z")

        second_start = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert second_start.status_code == 200
        assert second_start.json()["created"] is False
        assert second_start.json()["attempt"]["id"] == attempt["id"]

        after_start = client.get("/api/v1/participant/context", headers=auth(participant))
        assert after_start.json()["active_attempt"]["id"] == attempt["id"]

        skipped = client.post(
            f"/api/v1/contests/{contest_id}/codes",
            headers=auth(organizer),
            json={},
        )
        assert skipped.json()["generated_count"] == 0
        assert skipped.json()["skipped_count"] == 2

        rotated = client.post(
            f"/api/v1/contests/{contest_id}/codes",
            headers=auth(organizer),
            json={"rotate": True},
        )
        assert rotated.status_code == 200
        assert rotated.json()["generated_count"] == 2
        replacement_code = rotated.json()["items"][0]["code"]
        assert replacement_code != participant_code

        revoked_token = client.get("/api/v1/participant/context", headers=auth(participant))
        assert revoked_token.status_code == 401
        assert revoked_token.json()["detail"]["code"] == "ACCESS_REVOKED"

        old_code = client.post("/api/v1/access/redeem", json={"code": participant_code})
        assert old_code.status_code == 401
        new_code = client.post("/api/v1/access/redeem", json={"code": replacement_code})
        assert new_code.status_code == 200


def test_expired_code_is_rejected(tmp_path):
    database_path = tmp_path / "expired.db"
    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={"title": "Короткий контест"},
        ).json()
        client.post(
            f"/api/v1/contests/{contest['id']}/enrollments",
            headers=auth(organizer),
            json={
                "participants": [
                    {"external_ref": "short-001", "display_name": "Участник"}
                ]
            },
        )
        code = client.post(
            f"/api/v1/contests/{contest['id']}/codes",
            headers=auth(organizer),
            json={},
        ).json()["items"][0]["code"]
        client.post(f"/api/v1/contests/{contest['id']}/publish", headers=auth(organizer))

        with application.state.database.session_factory() as session:
            stored_code = session.scalar(select(AccessCode))
            assert stored_code is not None
            stored_code.expires_at = utc_now() - timedelta(seconds=1)
            session.commit()

        rejected = client.post("/api/v1/access/redeem", json={"code": code})
        assert rejected.status_code == 401
        assert rejected.json()["detail"]["code"] == "INVALID_ACCESS_CODE"

        with application.state.database.session_factory() as session:
            assert session.scalar(select(AccessCode.status)) == AccessCodeStatus.EXPIRED
