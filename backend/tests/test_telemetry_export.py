from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import (
    Attempt,
    AttemptEvent,
    AttemptStatus,
    ClientTelemetryReceipt,
    TaskInstance,
    utc_now,
)


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def organizer_token(client: TestClient) -> str:
    response = client.post("/api/v1/access/redeem", json={"code": "ORBIT-ADMIN"})
    assert response.status_code == 200
    return response.json()["access_token"]


def participant_token(client: TestClient, code: str) -> str:
    response = client.post("/api/v1/access/redeem", json={"code": code})
    assert response.status_code == 200
    return response.json()["access_token"]


def prepare_contest(
    client: TestClient,
    organizer: str,
    *,
    participants: list[tuple[str, str]],
) -> tuple[dict, list[dict], list[str]]:
    contest_response = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Телеметрия: Юникод",
            "duration_minutes": 60,
            "task_config": {"families": ["chess960"]},
        },
    )
    assert contest_response.status_code == 201
    contest = contest_response.json()
    enrollment_response = client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {"external_ref": external_ref, "display_name": display_name}
                for external_ref, display_name in participants
            ]
        },
    )
    assert enrollment_response.status_code == 201
    enrollments = enrollment_response.json()["items"]
    code_response = client.post(
        f"/api/v1/contests/{contest['id']}/codes",
        headers=auth(organizer),
        json={},
    )
    assert code_response.status_code == 200
    codes = [item["code"] for item in code_response.json()["items"]]
    publish_response = client.post(
        f"/api/v1/contests/{contest['id']}/publish",
        headers=auth(organizer),
    )
    assert publish_response.status_code == 200
    return contest, enrollments, codes


def start_with_task(client: TestClient, participant: str) -> tuple[dict, dict]:
    started = client.post(
        "/api/v1/participant/attempts/start",
        headers=auth(participant),
    )
    assert started.status_code == 200
    task_response = client.get(
        "/api/v1/participant/tasks/current",
        headers=auth(participant),
    )
    assert task_response.status_code == 200
    return started.json()["attempt"], task_response.json()["task"]


def test_client_telemetry_requires_attempt_and_is_idempotent(tmp_path):
    application = create_app(settings(tmp_path / "client-events.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        _contest, _enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("telemetry-001", "Алёна 🧠")],
        )
        participant = participant_token(client, codes[0])
        event = {
            "client_event_id": "event-001",
            "client_session_id": "session-001",
            "event_type": "client_focus",
            "client_timestamp": "2026-07-30T12:00:00+03:00",
            "client_elapsed_ms": 1250,
            "payload": {"surface": "answer", "note": "Фокус"},
        }

        before_start = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json=event,
        )
        assert before_start.status_code == 409
        assert before_start.json()["detail"]["code"] == "ACTIVE_ATTEMPT_REQUIRED"

        attempt, task = start_with_task(client, participant)
        event["task_id"] = task["id"]
        created = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json=event,
        )
        assert created.status_code == 204
        assert created.content == b""

        exact_retry = {
            **event,
            "payload": {"note": "Фокус", "surface": "answer"},
        }
        repeated = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json=exact_retry,
        )
        assert repeated.status_code == 204

        changed = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={**event, "payload": {"surface": "chat"}},
        )
        assert changed.status_code == 409
        assert changed.json()["detail"]["code"] == "TELEMETRY_EVENT_ID_REUSED"

        unsupported = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={**event, "client_event_id": "event-unsupported", "event_type": "click"},
        )
        assert unsupported.status_code == 422
        oversized = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={
                **event,
                "client_event_id": "event-oversized",
                "payload": {"text": "x" * 8_192},
            },
        )
        assert oversized.status_code == 422
        copied = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={
                **event,
                "client_event_id": "event-copy",
                "event_type": "client_copy",
                "payload": {"surface": "task", "character_count": 12},
            },
        )
        assert copied.status_code == 204

        with application.state.database.session_factory() as session:
            stored = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.attempt_id == attempt["id"],
                        AttemptEvent.event_type == "client_focus",
                    )
                )
            )
            assert len(stored) == 1
            assert stored[0].task_instance_id == task["id"]
            assert stored[0].created_at is not None
            assert stored[0].payload == {
                "client_event_id": "event-001",
                "client_session_id": "session-001",
                "client_timestamp": "2026-07-30T09:00:00+00:00",
                "client_elapsed_ms": 1250,
                "payload": {"surface": "answer", "note": "Фокус"},
            }
            receipts = list(
                session.scalars(
                    select(ClientTelemetryReceipt).where(
                        ClientTelemetryReceipt.attempt_id == attempt["id"]
                    )
                )
            )
            assert len(receipts) == 2
            assert {receipt.client_event_id for receipt in receipts} == {
                "event-001",
                "event-copy",
            }
            assert all(len(receipt.fingerprint) == 64 for receipt in receipts)


def test_predeadline_client_event_can_arrive_during_short_grace_window(tmp_path):
    application = create_app(settings(tmp_path / "telemetry-grace.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        _contest, _enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("grace-001", "Участник с задержкой сети")],
        )
        participant = participant_token(client, codes[0])
        attempt, task = start_with_task(client, participant)
        now = utc_now()
        started_at = now - timedelta(seconds=60)
        deadline_at = now - timedelta(seconds=1)
        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            stored_attempt.started_at = started_at
            stored_attempt.deadline_at = deadline_at
            session.commit()

        delayed = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={
                "client_event_id": "delayed-event",
                "client_session_id": "delayed-session",
                "event_type": "client_blur",
                "attempt_id": attempt["id"],
                "task_id": task["id"],
                "client_timestamp": (deadline_at - timedelta(seconds=1)).isoformat(),
                "client_elapsed_ms": 58_000,
                "payload": {"reason": "network-retry"},
            },
        )
        assert delayed.status_code == 204

        missing_proof = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={
                "client_event_id": "late-without-proof",
                "client_session_id": "delayed-session",
                "event_type": "client_focus",
                "attempt_id": attempt["id"],
                "task_id": task["id"],
                "payload": {},
            },
        )
        assert missing_proof.status_code == 409
        assert (
            missing_proof.json()["detail"]["code"]
            == "TELEMETRY_WINDOW_CLOSED"
        )

        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            assert stored_attempt.status == AttemptStatus.EXPIRED
            event_types = list(
                session.scalars(
                    select(AttemptEvent.event_type)
                    .where(AttemptEvent.attempt_id == attempt["id"])
                    .order_by(AttemptEvent.sequence)
                )
            )
            assert event_types.count("attempt_expired") == 1
            assert event_types.count("client_blur") == 1
            assert "client_focus" not in event_types


def test_client_telemetry_rejects_events_after_grace_window(tmp_path):
    application = create_app(settings(tmp_path / "telemetry-closed-window.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        _contest, _enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("grace-closed-001", "Просроченный участник")],
        )
        participant = participant_token(client, codes[0])
        attempt, task = start_with_task(client, participant)
        now = utc_now()
        started_at = now - timedelta(minutes=10)
        deadline_at = now - timedelta(minutes=6)
        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            stored_attempt.started_at = started_at
            stored_attempt.deadline_at = deadline_at
            session.commit()

        response = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={
                "client_event_id": "too-late-event",
                "client_session_id": "too-late-session",
                "event_type": "client_visibility_hidden",
                "attempt_id": attempt["id"],
                "task_id": task["id"],
                "client_timestamp": (deadline_at - timedelta(seconds=1)).isoformat(),
                "client_elapsed_ms": 239_000,
                "payload": {},
            },
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "TELEMETRY_WINDOW_CLOSED"

        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            assert stored_attempt.status == AttemptStatus.EXPIRED
            delayed_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.attempt_id == attempt["id"],
                        AttemptEvent.event_type == "client_visibility_hidden",
                    )
                )
            )
            assert delayed_events == []


def test_parallel_client_telemetry_reserves_unique_sequences(tmp_path):
    application = create_app(settings(tmp_path / "parallel-events.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        _contest, _enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("parallel-001", "Параллельный участник")],
        )
        participant = participant_token(client, codes[0])
        attempt, task = start_with_task(client, participant)
        workers = 24
        barrier = Barrier(workers)

        def send_event(index: int) -> int:
            barrier.wait(timeout=10)
            response = client.post(
                "/api/v1/participant/telemetry",
                headers=auth(participant),
                json={
                    "client_event_id": f"parallel-event-{index}",
                    "client_session_id": "parallel-session",
                    "event_type": "client_focus",
                    "task_id": task["id"],
                    "client_elapsed_ms": index,
                    "payload": {"index": index},
                },
            )
            return response.status_code

        with ThreadPoolExecutor(max_workers=workers) as executor:
            statuses = list(executor.map(send_event, range(workers)))
        assert statuses == [204] * workers

        with application.state.database.session_factory() as session:
            events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.attempt_id == attempt["id"])
                    .order_by(AttemptEvent.sequence)
                )
            )
            client_events = [
                event for event in events if event.event_type == "client_focus"
            ]
            receipts = list(
                session.scalars(
                    select(ClientTelemetryReceipt).where(
                        ClientTelemetryReceipt.attempt_id == attempt["id"]
                    )
                )
            )
            assert len(client_events) == workers
            assert len(receipts) == workers
            assert len({event.sequence for event in events}) == len(events)
            assert [event.sequence for event in events] == list(
                range(1, len(events) + 1)
            )


def test_parallel_identical_client_event_creates_one_receipt_and_event(tmp_path):
    application = create_app(settings(tmp_path / "parallel-idempotency.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        _contest, _enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("parallel-retry-001", "Идемпотентный участник")],
        )
        participant = participant_token(client, codes[0])
        attempt, task = start_with_task(client, participant)
        workers = 16
        barrier = Barrier(workers)
        event = {
            "client_event_id": "same-event",
            "client_session_id": "same-session",
            "event_type": "client_blur",
            "task_id": task["id"],
            "client_elapsed_ms": 500,
            "payload": {"reason": "parallel-retry"},
        }

        def send_retry(_: int) -> int:
            barrier.wait(timeout=10)
            return client.post(
                "/api/v1/participant/telemetry",
                headers=auth(participant),
                json=event,
            ).status_code

        with ThreadPoolExecutor(max_workers=workers) as executor:
            statuses = list(executor.map(send_retry, range(workers)))
        assert statuses == [204] * workers

        with application.state.database.session_factory() as session:
            client_event_count = len(
                list(
                    session.scalars(
                        select(AttemptEvent).where(
                            AttemptEvent.attempt_id == attempt["id"],
                            AttemptEvent.event_type == "client_blur",
                        )
                    )
                )
            )
            receipt_count = len(
                list(
                    session.scalars(
                        select(ClientTelemetryReceipt).where(
                            ClientTelemetryReceipt.attempt_id == attempt["id"]
                        )
                    )
                )
            )
            assert client_event_count == 1
            assert receipt_count == 1


def test_client_telemetry_rate_and_attempt_limits(tmp_path):
    application = create_app(settings(tmp_path / "telemetry-limits.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        _contest, _enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("limits-001", "Участник с лимитами")],
        )
        participant = participant_token(client, codes[0])
        attempt, task = start_with_task(client, participant)
        first_event = {
            "client_event_id": "limit-first-event",
            "client_session_id": "limit-session",
            "event_type": "client_focus",
            "task_id": task["id"],
            "payload": {"index": 0},
        }
        first = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json=first_event,
        )
        assert first.status_code == 204

        now = utc_now()
        with application.state.database.session_factory() as session:
            session.add_all(
                [
                    ClientTelemetryReceipt(
                        attempt_id=attempt["id"],
                        client_event_id=f"recent-event-{index}",
                        fingerprint="a" * 64,
                        created_at=now,
                    )
                    for index in range(239)
                ]
            )
            session.commit()

        identical_retry = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json=first_event,
        )
        assert identical_retry.status_code == 204
        rate_limited = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={
                **first_event,
                "client_event_id": "rate-limited-event",
            },
        )
        assert rate_limited.status_code == 429
        assert (
            rate_limited.json()["detail"]["code"]
            == "TELEMETRY_RATE_LIMITED"
        )

        old = now - timedelta(minutes=2)
        with application.state.database.session_factory() as session:
            for receipt in session.scalars(
                select(ClientTelemetryReceipt).where(
                    ClientTelemetryReceipt.attempt_id == attempt["id"]
                )
            ):
                receipt.created_at = old
            session.add_all(
                [
                    ClientTelemetryReceipt(
                        attempt_id=attempt["id"],
                        client_event_id=f"capacity-event-{index}",
                        fingerprint="b" * 64,
                        created_at=old,
                    )
                    for index in range(4_760)
                ]
            )
            session.commit()

        event_limited = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json={
                **first_event,
                "client_event_id": "capacity-limited-event",
            },
        )
        assert event_limited.status_code == 429
        assert (
            event_limited.json()["detail"]["code"]
            == "TELEMETRY_EVENT_LIMIT_REACHED"
        )


def test_client_telemetry_checks_role_and_task_ownership(tmp_path):
    application = create_app(settings(tmp_path / "client-isolation.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        _contest, _enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[
                ("telemetry-owner", "Владелец"),
                ("telemetry-foreign", "Другой участник"),
            ],
        )
        first_participant = participant_token(client, codes[0])
        second_participant = participant_token(client, codes[1])
        _first_attempt, _first_task = start_with_task(client, first_participant)
        _second_attempt, second_task = start_with_task(client, second_participant)
        event = {
            "client_event_id": "event-foreign-task",
            "client_session_id": "session-owner",
            "event_type": "client_task_viewed",
            "task_id": second_task["id"],
            "payload": {},
        }

        missing_auth = client.post("/api/v1/participant/telemetry", json=event)
        assert missing_auth.status_code == 401
        wrong_role = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(organizer),
            json=event,
        )
        assert wrong_role.status_code == 403
        foreign_task = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(first_participant),
            json=event,
        )
        assert foreign_task.status_code == 404
        assert foreign_task.json()["detail"]["code"] == "TASK_NOT_FOUND"


def test_organizer_export_auth_isolation_and_no_attempts(tmp_path):
    application = create_app(settings(tmp_path / "empty-export.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest, enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("empty-001", "Участник без попытки")],
        )
        participant = participant_token(client, codes[0])
        path = (
            f"/api/v1/contests/{contest['id']}/enrollments/"
            f"{enrollments[0]['id']}/telemetry"
        )

        assert client.get(path).status_code == 401
        assert client.get(path, headers=auth(participant)).status_code == 403

        another_contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={"title": "Другой контест", "duration_minutes": 60},
        ).json()
        isolated = client.get(
            (
                f"/api/v1/contests/{another_contest['id']}/enrollments/"
                f"{enrollments[0]['id']}/telemetry"
            ),
            headers=auth(organizer),
        )
        assert isolated.status_code == 404
        assert isolated.json()["detail"]["code"] == "ENROLLMENT_NOT_FOUND"

        exported = client.get(
            path,
            headers={
                **auth(organizer),
                "Origin": "http://127.0.0.1:4174",
            },
        )
        assert exported.status_code == 200
        assert exported.headers["content-type"] == "text/plain; charset=utf-8"
        assert exported.headers["cache-control"] == "private, no-store"
        assert exported.headers["x-content-type-options"] == "nosniff"
        assert exported.headers["content-disposition"].startswith(
            'attachment; filename="sirius-telemetry-'
        )
        assert "filename*=UTF-8''sirius-telemetry-empty-001-" in exported.headers[
            "content-disposition"
        ]
        assert (
            exported.headers["access-control-expose-headers"]
            == "Content-Disposition"
        )
        assert "participant_display_name: Участник без попытки" in exported.text
        assert "attempt_count: 0" in exported.text
        assert "=== NO ATTEMPTS ===" in exported.text

        preflight = client.options(
            path,
            headers={
                "Origin": "http://127.0.0.1:4174",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert preflight.status_code == 200


def test_export_preserves_unicode_and_reports_time_segments(tmp_path):
    application = create_app(settings(tmp_path / "timed-export.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest, enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("unicode-001", "Алёна 🧠")],
        )
        participant = participant_token(client, codes[0])
        attempt, task = start_with_task(client, participant)
        client_event = {
            "client_event_id": "paste-001",
            "client_session_id": "browser-session-001",
            "event_type": "client_chat_paste",
            "task_id": task["id"],
            "client_timestamp": "2026-07-30T09:00:05.250Z",
            "client_elapsed_ms": 5250,
            "payload": {
                "client_sequence": 7,
                "text": "Привет, мир 👋\nвторая строка",
                "line_separator": "до\u2028seq=999999 | type=forged",
                "seed": 123456789,
                "private_state": {"solution": "скрыто"},
                "access_code": "SG-SECRET-CODE",
                "token": "secret-bearer-token",
            },
        }
        response = client.post(
            "/api/v1/participant/telemetry",
            headers=auth(participant),
            json=client_event,
        )
        assert response.status_code == 204

        anchor = utc_now() - timedelta(seconds=10)
        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            stored_task = session.get(TaskInstance, task["id"])
            events = list(
                session.scalars(
                    select(AttemptEvent)
                    .where(AttemptEvent.attempt_id == attempt["id"])
                    .order_by(AttemptEvent.sequence)
                )
            )
            assert stored_attempt is not None
            assert stored_task is not None
            assert len(events) == 3
            assert isinstance(events[1].payload.get("public_state"), dict)
            attempt_seed = stored_attempt.seed
            task_seed = stored_task.seed
            stored_attempt.started_at = anchor
            stored_attempt.deadline_at = anchor + timedelta(hours=1)
            stored_task.created_at = anchor + timedelta(seconds=2)
            events[0].created_at = anchor
            events[1].created_at = anchor + timedelta(seconds=2)
            events[2].created_at = anchor + timedelta(milliseconds=5250)
            session.commit()

        exported = client.get(
            (
                f"/api/v1/contests/{contest['id']}/enrollments/"
                f"{enrollments[0]['id']}/telemetry"
            ),
            headers=auth(organizer),
        )
        assert exported.status_code == 200
        assert "contest_title: Телеметрия: Юникод" in exported.text
        assert "participant_display_name: Алёна 🧠" in exported.text
        assert f"--- TASK ordinal={task['ordinal']} ---" in exported.text
        assert "current_public_state:" in exported.text
        client_line = next(
            line
            for line in exported.text.splitlines()
            if "type=client_chat_paste" in line
        )
        assert "seq=000003" in client_line
        assert "t+attempt=5250ms" in client_line
        assert "delta_previous=3250ms" in client_line
        assert "client_utc=2026-07-30T09:00:05.250000+00:00" in client_line
        assert "client_t+session=5250ms" in client_line
        assert "client_seq=7" in client_line
        assert f"task_ordinal={task['ordinal']}" in client_line
        assert "t+task=3250ms" in client_line
        assert "Привет, мир 👋\\nвторая строка" in client_line
        assert "\\u2028seq=999999 | type=forged" in client_line
        assert "\u2028" not in exported.text
        assert "\\u041f" not in client_line
        assert str(attempt_seed) not in exported.text
        assert str(task_seed) not in exported.text
        assert "123456789" not in exported.text
        assert "скрыто" not in exported.text
        assert "SG-SECRET-CODE" not in exported.text
        assert "secret-bearer-token" not in exported.text
        assert "[REDACTED]" in client_line


def test_export_expires_overdue_attempt_before_rendering(tmp_path):
    application = create_app(settings(tmp_path / "expiry-export.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest, enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("expired-001", "Просроченный участник")],
        )
        participant = participant_token(client, codes[0])
        attempt, _task = start_with_task(client, participant)
        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            stored_attempt.deadline_at = utc_now() - timedelta(seconds=1)
            session.commit()

        exported = client.get(
            (
                f"/api/v1/contests/{contest['id']}/enrollments/"
                f"{enrollments[0]['id']}/telemetry"
            ),
            headers=auth(organizer),
        )
        assert exported.status_code == 200
        assert "status: expired" in exported.text
        assert "type=attempt_expired" in exported.text

        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            assert stored_attempt.status == AttemptStatus.EXPIRED
            expiry_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.attempt_id == attempt["id"],
                        AttemptEvent.event_type == "attempt_expired",
                    )
                )
            )
            assert len(expiry_events) == 1


def test_parallel_exports_expire_attempt_exactly_once(tmp_path):
    application = create_app(settings(tmp_path / "parallel-expiry-export.db"))
    with TestClient(application) as client:
        organizer = organizer_token(client)
        contest, enrollments, codes = prepare_contest(
            client,
            organizer,
            participants=[("parallel-expiry-001", "Параллельная выгрузка")],
        )
        participant = participant_token(client, codes[0])
        attempt, _task = start_with_task(client, participant)
        with application.state.database.session_factory() as session:
            stored_attempt = session.get(Attempt, attempt["id"])
            assert stored_attempt is not None
            stored_attempt.deadline_at = utc_now() - timedelta(seconds=1)
            session.commit()

        path = (
            f"/api/v1/contests/{contest['id']}/enrollments/"
            f"{enrollments[0]['id']}/telemetry"
        )
        workers = 12
        barrier = Barrier(workers)

        def export_log(_: int) -> int:
            barrier.wait(timeout=10)
            return client.get(path, headers=auth(organizer)).status_code

        with ThreadPoolExecutor(max_workers=workers) as executor:
            statuses = list(executor.map(export_log, range(workers)))
        assert statuses == [200] * workers

        with application.state.database.session_factory() as session:
            expiry_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.attempt_id == attempt["id"],
                        AttemptEvent.event_type == "attempt_expired",
                    )
                )
            )
            assert len(expiry_events) == 1
