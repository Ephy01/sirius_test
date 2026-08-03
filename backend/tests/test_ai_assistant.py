"""API battery for the Alice AI assistant endpoint (ТЗ Alice AI §22.2).

Все сценарии выполняются на fake provider — без обращений к сети.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai import FakeAssistantProvider, ProviderError
from app.config import Settings
from app.main import create_app
from app.models import AiTurn, AiTurnStatus, Attempt, AttemptEvent, utc_now


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _settings(database_path, *, ai_enabled: bool = True) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
        ai_enabled=ai_enabled,
        yandex_ai_model_uri="gpt://test-folder/aliceai-llm",
        # Ключ не задан: create_app не создаёт сетевой провайдер,
        # тесты подставляют fake через app.state.ai_provider.
    )


DEFAULT_AI_CONFIG = {
    "enabled": True,
    "mode": "socratic",
    "max_turns_per_attempt": 15,
    "max_turns_per_task": 5,
}


def _task_config(ai: dict | None) -> dict:
    config: dict = {
        "families": [
            {
                "family": "token_zendo",
                "weight": 1,
                "initial_difficulty": 2,
                "max_difficulty": 5,
            }
        ],
    }
    if ai is not None:
        config["ai"] = ai
    return config


def _prepare(client, *, ai: dict | None, external_ref: str = "ai-001") -> tuple[str, str]:
    organizer = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    ).json()["access_token"]
    contest = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={"title": "AI пилот", "task_config": _task_config(ai)},
    ).json()
    client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {"external_ref": external_ref, "display_name": "Испытатель"}
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
    return participant, organizer


def _start_task(client, participant) -> dict:
    client.post("/api/v1/participant/attempts/start", headers=auth(participant))
    return client.get(
        "/api/v1/participant/tasks/current",
        headers=auth(participant),
    ).json()["task"]


def _send(client, participant, task_id, message, action_id="turn-1"):
    return client.post(
        f"/api/v1/participant/tasks/{task_id}/ai/turns",
        headers=auth(participant),
        json={"clientActionId": action_id, "message": message},
    )


def test_successful_turn_returns_answer_and_context_is_safe(tmp_path):
    application = create_app(_settings(tmp_path / "ai-ok.db"))
    fake = FakeAssistantProvider(reply="Сравните числа на фишках.")
    application.state.ai_provider = fake
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)

        response = _send(client, participant, task["id"], "С чего начать анализ?")
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"
        assert body["assistantMessage"] == "Сравните числа на фишках."
        assert body["usage"]["totalTokens"] == 142
        assert body["remaining"] == {"task": 4, "attempt": 14}

        # Сценарий 14: скрытые данные не попали в запрос провайдеру.
        assert len(fake.requests) == 1
        request = fake.requests[0]
        assert '"target_answers"' not in request.context_text
        assert '"rule_index"' not in request.context_text
        assert "socratic" in request.system_prompt
        assert request.user_message == "С чего начать анализ?"
        assert '"family":"token_zendo"' in request.context_text

        # Телеметрия: события есть, полного текста диалога в них нет.
        with application.state.database.session_factory() as session:
            events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type.in_(
                            ["ai_turn_requested", "ai_turn_completed"]
                        )
                    )
                )
            )
            assert {event.event_type for event in events} == {
                "ai_turn_requested",
                "ai_turn_completed",
            }
            for event in events:
                assert "С чего начать анализ?" not in str(event.payload)


def test_ai_disabled_in_contest(tmp_path):
    application = create_app(_settings(tmp_path / "ai-disabled.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=None)
        task = _start_task(client, participant)
        response = _send(client, participant, task["id"], "Привет")
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "AI_DISABLED"


def test_ai_not_configured_globally(tmp_path):
    application = create_app(
        _settings(tmp_path / "ai-unconfigured.db", ai_enabled=False)
    )
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        response = _send(client, participant, task["id"], "Привет")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "AI_NOT_CONFIGURED"


def test_expired_attempt_rejects_turn(tmp_path):
    application = create_app(_settings(tmp_path / "ai-expired.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        with application.state.database.session_factory() as session:
            attempt = session.scalars(select(Attempt)).one()
            attempt.deadline_at = utc_now() - timedelta(minutes=1)
            session.commit()
        response = _send(client, participant, task["id"], "Ещё можно?")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ACTIVE_ATTEMPT_REQUIRED"


def test_closed_task_rejects_turn(tmp_path):
    application = create_app(_settings(tmp_path / "ai-closed.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        client.post(
            f"/api/v1/participant/tasks/{task['id']}/answer",
            headers=auth(participant),
            json={"answer": "да да да да да да да да"},
        )
        response = _send(client, participant, task["id"], "Как решить?")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "TASK_ALREADY_CLOSED"


def test_foreign_task_is_not_found(tmp_path):
    application = create_app(_settings(tmp_path / "ai-foreign.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        first, _ = _prepare(client, ai=DEFAULT_AI_CONFIG, external_ref="ai-first")
        first_task = _start_task(client, first)
        second, _ = _prepare(client, ai=DEFAULT_AI_CONFIG, external_ref="ai-second")
        _start_task(client, second)
        response = _send(client, second, first_task["id"], "Чужая задача")
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "TASK_NOT_FOUND"


def test_task_turn_limit(tmp_path):
    application = create_app(_settings(tmp_path / "ai-task-limit.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(
            client, ai={**DEFAULT_AI_CONFIG, "max_turns_per_task": 1}
        )
        task = _start_task(client, participant)
        first = _send(client, participant, task["id"], "Раз", action_id="t1")
        assert first.status_code == 200
        assert first.json()["remaining"]["task"] == 0
        second = _send(client, participant, task["id"], "Два", action_id="t2")
        assert second.status_code == 429
        assert second.json()["detail"]["code"] == "AI_TURN_LIMIT_REACHED"


def test_attempt_turn_limit(tmp_path):
    application = create_app(_settings(tmp_path / "ai-attempt-limit.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(
            client, ai={**DEFAULT_AI_CONFIG, "max_turns_per_attempt": 1}
        )
        task = _start_task(client, participant)
        assert _send(client, participant, task["id"], "Раз", "a1").status_code == 200
        blocked = _send(client, participant, task["id"], "Два", "a2")
        assert blocked.status_code == 429
        assert blocked.json()["detail"]["code"] == "AI_TURN_LIMIT_REACHED"


def test_client_action_id_replay_returns_same_turn(tmp_path):
    application = create_app(_settings(tmp_path / "ai-replay.db"))
    fake = FakeAssistantProvider()
    application.state.ai_provider = fake
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        first = _send(client, participant, task["id"], "Вопрос", "same-id")
        replay = _send(client, participant, task["id"], "Вопрос", "same-id")
        assert first.status_code == replay.status_code == 200
        assert first.json()["id"] == replay.json()["id"]
        assert len(fake.requests) == 1  # модель вызвана один раз


def test_second_concurrent_request_is_blocked(tmp_path):
    application = create_app(_settings(tmp_path / "ai-pending.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        with application.state.database.session_factory() as session:
            attempt = session.scalars(select(Attempt)).one()
            session.add(
                AiTurn(
                    attempt_id=attempt.id,
                    task_instance_id=task["id"],
                    sequence=1,
                    client_action_id="in-flight",
                    status=AiTurnStatus.PENDING,
                    user_message="висящий запрос",
                    model_uri="gpt://test-folder/aliceai-llm",
                    prompt_version="sirius-assistant-socratic-v1",
                    public_context_hash="0" * 64,
                )
            )
            session.commit()
        response = _send(client, participant, task["id"], "Второй", "next-id")
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "AI_TURN_IN_PROGRESS"


def test_provider_timeout_maps_to_504_and_keeps_limit(tmp_path):
    application = create_app(_settings(tmp_path / "ai-timeout.db"))
    application.state.ai_provider = FakeAssistantProvider(
        error=ProviderError("AI_PROVIDER_TIMEOUT", "timeout")
    )
    with TestClient(application) as client:
        participant, _ = _prepare(
            client, ai={**DEFAULT_AI_CONFIG, "max_turns_per_task": 1}
        )
        task = _start_task(client, participant)
        failed = _send(client, participant, task["id"], "Долгий", "f1")
        assert failed.status_code == 504
        assert failed.json()["detail"]["code"] == "AI_PROVIDER_TIMEOUT"

        # Неуспешный вызов не тратит пользовательский лимит.
        application.state.ai_provider = FakeAssistantProvider()
        retry = _send(client, participant, task["id"], "Повтор", "f2")
        assert retry.status_code == 200, retry.text

        with application.state.database.session_factory() as session:
            failed_events = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "ai_turn_failed"
                    )
                )
            )
            assert len(failed_events) == 1
            assert failed_events[0].payload["errorCode"] == "AI_PROVIDER_TIMEOUT"


def test_provider_error_maps_to_503(tmp_path):
    application = create_app(_settings(tmp_path / "ai-unavailable.db"))
    application.state.ai_provider = FakeAssistantProvider(
        error=ProviderError("AI_PROVIDER_UNAVAILABLE", "down")
    )
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        response = _send(client, participant, task["id"], "Кто там?")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "AI_PROVIDER_UNAVAILABLE"


def test_message_too_long(tmp_path):
    application = create_app(_settings(tmp_path / "ai-long.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(
            client, ai={**DEFAULT_AI_CONFIG, "max_input_characters": 100}
        )
        task = _start_task(client, participant)
        response = _send(client, participant, task["id"], "х" * 200)
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "AI_MESSAGE_TOO_LONG"


def test_history_restores_dialogue(tmp_path):
    application = create_app(_settings(tmp_path / "ai-history.db"))
    application.state.ai_provider = FakeAssistantProvider(reply="Ответ ассистента.")
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        _send(client, participant, task["id"], "Первый вопрос", "h1")
        _send(client, participant, task["id"], "Второй вопрос", "h2")

        history = client.get(
            f"/api/v1/participant/tasks/{task['id']}/ai/turns",
            headers=auth(participant),
        )
        assert history.status_code == 200, history.text
        body = history.json()
        assert [turn["userMessage"] for turn in body["turns"]] == [
            "Первый вопрос",
            "Второй вопрос",
        ]
        assert all(
            turn["assistantMessage"] == "Ответ ассистента." for turn in body["turns"]
        )
        assert body["remaining"]["task"] == 3


def test_history_is_sent_to_provider(tmp_path):
    application = create_app(_settings(tmp_path / "ai-history-ctx.db"))
    fake = FakeAssistantProvider(reply="Идём дальше.")
    application.state.ai_provider = fake
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        _send(client, participant, task["id"], "Первый", "c1")
        _send(client, participant, task["id"], "Второй", "c2")
        assert len(fake.requests) == 2
        second_request = fake.requests[1]
        assert [message.content for message in second_request.history] == [
            "Первый",
            "Идём дальше.",
        ]


def test_organizer_export_contains_ai_transcript(tmp_path):
    application = create_app(_settings(tmp_path / "ai-export.db"))
    application.state.ai_provider = FakeAssistantProvider(
        reply="Какие степени у вершин?"
    )
    with TestClient(application) as client:
        participant, organizer = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        _send(client, participant, task["id"], "Правило про степени?")

        with application.state.database.session_factory() as session:
            attempt = session.scalars(select(Attempt)).one()
            contest_id = attempt.enrollment.contest_id
            enrollment_id = attempt.enrollment_id

        export = client.get(
            f"/api/v1/contests/{contest_id}/enrollments/{enrollment_id}/telemetry",
            headers=auth(organizer),
        )
        assert export.status_code == 200, export.text
        text = export.text
        assert "--- AI TRANSCRIPT ---" in text
        assert "Правило про степени?" in text
        assert "Какие степени у вершин?" in text
        assert "prompt_version: sirius-assistant-socratic-v2" in text
        assert "--- AI SUMMARY ---" in text
        assert "ai_turns_completed: 1" in text
