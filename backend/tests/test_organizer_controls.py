import re
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from app.config import Settings
from app.database import Base, Database
from app.main import create_app
from app.models import (
    AccessCode,
    AccessCodeStatus,
    Attempt,
    AttemptEvent,
    AttemptGrant,
    AttemptGrantStatus,
    TaskInstance,
    utc_now,
)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def organizer_token(client: TestClient) -> str:
    response = client.post("/api/v1/access/redeem", json={"code": "ORBIT-ADMIN"})
    assert response.status_code == 200
    return response.json()["access_token"]


def create_contest_with_participants(
    client: TestClient,
    organizer: str,
    *,
    title: str,
    refs: list[str],
) -> tuple[str, list[dict], list[str]]:
    contest = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={"title": title, "duration_minutes": 60},
    )
    assert contest.status_code == 201
    contest_id = contest.json()["id"]

    enrollment_response = client.post(
        f"/api/v1/contests/{contest_id}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {"external_ref": ref, "display_name": f"Участник {ref}"}
                for ref in refs
            ]
        },
    )
    assert enrollment_response.status_code == 201
    enrollments = enrollment_response.json()["items"]

    code_response = client.post(
        f"/api/v1/contests/{contest_id}/codes",
        headers=auth(organizer),
        json={},
    )
    assert code_response.status_code == 200
    codes = [item["code"] for item in code_response.json()["items"]]

    published = client.post(
        f"/api/v1/contests/{contest_id}/publish",
        headers=auth(organizer),
    )
    assert published.status_code == 200
    return contest_id, enrollments, codes


def participant_token(client: TestClient, code: str) -> str:
    response = client.post("/api/v1/access/redeem", json={"code": code})
    assert response.status_code == 200
    return response.json()["access_token"]


def assert_key_absent(value, forbidden_key: str) -> None:
    if isinstance(value, dict):
        assert forbidden_key not in value
        for child in value.values():
            assert_key_absent(child, forbidden_key)
    elif isinstance(value, list):
        for child in value:
            assert_key_absent(child, forbidden_key)


def test_create_all_adds_attempt_grants_table_to_existing_sqlite(tmp_path):
    database_path = tmp_path / "existing.db"
    database = Database(f"sqlite:///{database_path}")
    legacy_tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name != AttemptGrant.__tablename__
    ]
    Base.metadata.create_all(database.engine, tables=legacy_tables)
    assert AttemptGrant.__tablename__ not in inspect(database.engine).get_table_names()
    database.dispose()

    settings = Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert AttemptGrant.__tablename__ in inspect(
            client.app.state.database.engine
        ).get_table_names()


def test_organizer_list_normalizes_expiry_without_leaking_secrets(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'list.db'}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest_id, enrollments, codes = create_contest_with_participants(
            client,
            organizer,
            title="Статусы",
            refs=["list-001"],
        )
        participant = participant_token(client, codes[0])
        started = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert started.status_code == 200
        attempt_id = started.json()["attempt"]["id"]

        with application.state.database.session_factory() as session:
            stored_code = session.scalar(select(AccessCode))
            attempt = session.get(Attempt, attempt_id)
            assert stored_code is not None
            assert attempt is not None
            stored_code.expires_at = utc_now() - timedelta(seconds=1)
            attempt.deadline_at = utc_now() - timedelta(seconds=1)
            session.commit()

        listed = client.get(
            f"/api/v1/contests/{contest_id}/enrollments",
            headers=auth(organizer),
        )
        assert listed.status_code == 200
        payload = listed.json()
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["id"] == enrollments[0]["id"]
        assert item["participant"]["external_ref"] == "list-001"
        assert item["latest_code"]["status"] == "expired"
        assert item["latest_code"]["last4"] == codes[0][-4:]
        assert item["latest_attempt"]["id"] == attempt_id
        assert item["latest_attempt"]["status"] == "expired"
        assert item["attempt_grant_pending"] is False
        assert codes[0] not in listed.text
        assert_key_absent(payload, "lookup_hash")
        assert_key_absent(payload, "code")
        assert_key_absent(payload, "seed")

        with application.state.database.session_factory() as session:
            stored_code = session.scalar(select(AccessCode))
            attempt = session.get(Attempt, attempt_id)
            events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.attempt_id == attempt_id)
                    .order_by(AttemptEvent.sequence)
                )
            )
            assert stored_code is not None
            assert stored_code.status == AccessCodeStatus.EXPIRED
            assert attempt is not None
            assert attempt.status.value == "expired"
            assert [event.event_type for event in events][-1] == "attempt_expired"


def test_per_enrollment_rotation_is_isolated_and_invalidates_old_access(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'rotate.db'}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest_id, enrollments, codes = create_contest_with_participants(
            client,
            organizer,
            title="Ротация",
            refs=["rotate-001", "rotate-002"],
        )
        first_token = participant_token(client, codes[0])
        second_token = participant_token(client, codes[1])
        first_enrollment_id = enrollments[0]["id"]

        unauthenticated = client.post(
            (
                f"/api/v1/contests/{contest_id}/enrollments/"
                f"{first_enrollment_id}/codes/rotate"
            ),
            json={},
        )
        assert unauthenticated.status_code == 401
        forbidden = client.post(
            (
                f"/api/v1/contests/{contest_id}/enrollments/"
                f"{first_enrollment_id}/codes/rotate"
            ),
            headers=auth(first_token),
            json={},
        )
        assert forbidden.status_code == 403

        other_contest_id, _, _ = create_contest_with_participants(
            client,
            organizer,
            title="Другой контест",
            refs=["rotate-other"],
        )
        wrong_owner = client.post(
            (
                f"/api/v1/contests/{other_contest_id}/enrollments/"
                f"{first_enrollment_id}/codes/rotate"
            ),
            headers=auth(organizer),
            json={},
        )
        assert wrong_owner.status_code == 404
        assert wrong_owner.json()["detail"]["code"] == "ENROLLMENT_NOT_FOUND"

        rotated = client.post(
            (
                f"/api/v1/contests/{contest_id}/enrollments/"
                f"{first_enrollment_id}/codes/rotate"
            ),
            headers=auth(organizer),
            json={},
        )
        assert rotated.status_code == 200
        new_code = rotated.json()["code"]
        assert re.fullmatch(r"SG-[A-HJ-KM-NP-Z2-9]{4}-[A-HJ-KM-NP-Z2-9]{4}", new_code)
        assert new_code != codes[0]

        old_plaintext = client.post("/api/v1/access/redeem", json={"code": codes[0]})
        assert old_plaintext.status_code == 401
        old_session = client.get(
            "/api/v1/participant/context",
            headers=auth(first_token),
        )
        assert old_session.status_code == 401
        assert old_session.json()["detail"]["code"] == "ACCESS_REVOKED"
        unaffected_session = client.get(
            "/api/v1/participant/context",
            headers=auth(second_token),
        )
        assert unaffected_session.status_code == 200
        assert participant_token(client, new_code)

        with application.state.database.session_factory() as session:
            first_codes = list(
                session.scalars(
                    select(AccessCode)
                    .where(AccessCode.enrollment_id == first_enrollment_id)
                    .order_by(AccessCode.created_at)
                )
            )
            second_codes = list(
                session.scalars(
                    select(AccessCode).where(
                        AccessCode.enrollment_id == enrollments[1]["id"]
                    )
                )
            )
            assert [code.status for code in first_codes] == [
                AccessCodeStatus.REVOKED,
                AccessCodeStatus.ACTIVE,
            ]
            assert [code.status for code in second_codes] == [AccessCodeStatus.ACTIVE]


def test_attempt_grant_is_idempotent_consumed_once_and_preserves_history(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'grant.db'}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )
    application = create_app(settings)
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest_id, enrollments, codes = create_contest_with_participants(
            client,
            organizer,
            title="Повторная попытка",
            refs=["grant-001"],
        )
        enrollment_id = enrollments[0]["id"]
        participant = participant_token(client, codes[0])

        first_start = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert first_start.status_code == 200
        first_attempt = first_start.json()["attempt"]
        first_task_response = client.get(
            "/api/v1/participant/tasks/current",
            headers=auth(participant),
        )
        assert first_task_response.status_code == 200
        first_task_id = first_task_response.json()["task"]["id"]

        while_active = client.post(
            (
                f"/api/v1/contests/{contest_id}/enrollments/"
                f"{enrollment_id}/attempts/grant"
            ),
            headers=auth(organizer),
        )
        assert while_active.status_code == 409
        assert while_active.json()["detail"]["code"] == "ATTEMPT_ALREADY_ACTIVE"

        with application.state.database.session_factory() as session:
            attempt = session.get(Attempt, first_attempt["id"])
            assert attempt is not None
            first_attempt_seed = attempt.seed
            attempt.deadline_at = utc_now() - timedelta(seconds=1)
            original_event_ids = set(
                session.scalars(
                    select(AttemptEvent.id).where(
                        AttemptEvent.attempt_id == first_attempt["id"]
                    )
                )
            )
            session.commit()

        grant_path = (
            f"/api/v1/contests/{contest_id}/enrollments/"
            f"{enrollment_id}/attempts/grant"
        )
        granted = client.post(grant_path, headers=auth(organizer))
        assert granted.status_code == 200
        assert granted.json()["pending"] is True
        assert granted.json()["created"] is True
        granted_again = client.post(grant_path, headers=auth(organizer))
        assert granted_again.status_code == 200
        assert granted_again.json()["pending"] is True
        assert granted_again.json()["created"] is False
        assert granted_again.json()["granted_at"] == granted.json()["granted_at"]

        pending_list = client.get(
            f"/api/v1/contests/{contest_id}/enrollments",
            headers=auth(organizer),
        )
        assert pending_list.status_code == 200
        assert pending_list.json()["items"][0]["attempt_grant_pending"] is True
        assert pending_list.json()["items"][0]["latest_attempt"]["status"] == "expired"

        second_start = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert second_start.status_code == 200
        assert second_start.json()["created"] is True
        second_attempt = second_start.json()["attempt"]
        assert second_attempt["number"] == 2
        assert second_attempt["id"] != first_attempt["id"]
        assert "seed" not in second_attempt
        with application.state.database.session_factory() as session:
            stored_second_attempt = session.get(Attempt, second_attempt["id"])
            assert stored_second_attempt is not None
            assert stored_second_attempt.seed != first_attempt_seed

        consumed_list = client.get(
            f"/api/v1/contests/{contest_id}/enrollments",
            headers=auth(organizer),
        )
        item = consumed_list.json()["items"][0]
        assert item["attempt_grant_pending"] is False
        assert item["latest_attempt"]["id"] == second_attempt["id"]
        assert_key_absent(item["latest_attempt"], "seed")

        with application.state.database.session_factory() as session:
            grants = list(
                session.scalars(
                    select(AttemptGrant).where(
                        AttemptGrant.enrollment_id == enrollment_id
                    )
                )
            )
            assert len(grants) == 1
            assert grants[0].status == AttemptGrantStatus.CONSUMED
            assert grants[0].pending_slot is None
            assert grants[0].consumed_attempt_id == second_attempt["id"]

            old_task = session.get(TaskInstance, first_task_id)
            old_event_ids_after = set(
                session.scalars(
                    select(AttemptEvent.id).where(
                        AttemptEvent.attempt_id == first_attempt["id"]
                    )
                )
            )
            second_events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.attempt_id == second_attempt["id"])
                    .order_by(AttemptEvent.sequence)
                )
            )
            assert old_task is not None
            assert original_event_ids <= old_event_ids_after
            assert second_events[0].event_type == "attempt_started"
            assert second_events[0].payload["source"] == "organizer_grant"

        with application.state.database.session_factory() as session:
            attempt = session.get(Attempt, second_attempt["id"])
            assert attempt is not None
            attempt.deadline_at = utc_now() - timedelta(seconds=1)
            session.commit()
        no_second_grant = client.post(
            "/api/v1/participant/attempts/start",
            headers=auth(participant),
        )
        assert no_second_grant.status_code == 409
        assert no_second_grant.json()["detail"]["code"] == "ATTEMPT_NOT_AVAILABLE"


def test_attempt_grant_requires_organizer_and_contest_ownership(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'ownership.db'}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )
    with TestClient(create_app(settings)) as client:
        organizer = organizer_token(client)
        first_contest, enrollments, first_codes = create_contest_with_participants(
            client,
            organizer,
            title="Первый",
            refs=["owner-001"],
        )
        second_contest, _, _ = create_contest_with_participants(
            client,
            organizer,
            title="Второй",
            refs=["owner-002"],
        )
        enrollment_id = enrollments[0]["id"]
        participant = participant_token(client, first_codes[0])
        path = (
            f"/api/v1/contests/{first_contest}/enrollments/"
            f"{enrollment_id}/attempts/grant"
        )

        assert client.post(path).status_code == 401
        assert client.post(path, headers=auth(participant)).status_code == 403
        wrong_owner = client.post(
            (
                f"/api/v1/contests/{second_contest}/enrollments/"
                f"{enrollment_id}/attempts/grant"
            ),
            headers=auth(organizer),
        )
        assert wrong_owner.status_code == 404
        assert wrong_owner.json()["detail"]["code"] == "ENROLLMENT_NOT_FOUND"
