"""Crisis tripwire: словарный фильтр перед вызовом модели."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai import CRISIS_CATEGORY, FakeAssistantProvider, crisis_category
from app.main import create_app
from app.models import AttemptEvent

from tests.test_ai_assistant import (
    DEFAULT_AI_CONFIG,
    _prepare,
    _send,
    _settings,
    _start_task,
    auth,
)

TRIGGERING_MESSAGES = [
    "Я хочу покончить с собой",
    "думаю о суициде постоянно",
    "НЕ ХОЧУ БОЛЬШЕ ЖИТЬ",
    "кажется, я вскрою себе вены",
    "мысли о самоубийстве мешают решать",
    "иногда хочется умереть",
]

SAFE_MESSAGES = [
    "Хочу покончить с этой задачей побыстрее",
    "Правило связано с жизненным циклом графа?",
    "Убить двух зайцев: проверить пробу и цель",
    "не хочу жить в неведении, дайте подсказку про рёбра",
]


def test_crisis_category_detects_and_ignores():
    for message in TRIGGERING_MESSAGES:
        assert crisis_category(message) == CRISIS_CATEGORY, message
    for message in SAFE_MESSAGES[:3]:
        assert crisis_category(message) is None, message


def test_crisis_message_gets_support_without_model_call(tmp_path):
    application = create_app(_settings(tmp_path / "tripwire.db"))
    fake = FakeAssistantProvider()
    application.state.ai_provider = fake
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)

        response = _send(
            client, participant, task["id"], "Я хочу покончить с собой", "cr-1"
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "completed"
        assert "8-800-2000-122" in body["assistantMessage"]
        assert fake.requests == []
        assert body["remaining"] == {"task": 5, "attempt": 15}

        with application.state.database.session_factory() as session:
            flagged = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "ai_message_flagged"
                    )
                )
            )
            assert len(flagged) == 1
            assert flagged[0].payload["category"] == CRISIS_CATEGORY
            assert flagged[0].payload["aiTurnId"] == body["id"]
            assert "покончить" not in str(flagged[0].payload)

        history = client.get(
            f"/api/v1/participant/tasks/{task['id']}/ai/turns",
            headers=auth(participant),
        ).json()
        assert len(history["turns"]) == 1
        assert "8-800-2000-122" in history["turns"][0]["assistantMessage"]

        normal = _send(client, participant, task["id"], "Как искать правило?", "cr-2")
        assert normal.status_code == 200
        assert len(fake.requests) == 1


def test_crisis_replay_is_idempotent(tmp_path):
    application = create_app(_settings(tmp_path / "tripwire-replay.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(client, ai=DEFAULT_AI_CONFIG)
        task = _start_task(client, participant)
        first = _send(client, participant, task["id"], "не хочу жить", "same")
        replay = _send(client, participant, task["id"], "не хочу жить", "same")
        assert first.json()["id"] == replay.json()["id"]
        with application.state.database.session_factory() as session:
            flagged = list(
                session.scalars(
                    select(AttemptEvent).where(
                        AttemptEvent.event_type == "ai_message_flagged"
                    )
                )
            )
            assert len(flagged) == 1


def test_crisis_support_works_even_after_limit(tmp_path):
    application = create_app(_settings(tmp_path / "tripwire-limit.db"))
    application.state.ai_provider = FakeAssistantProvider()
    with TestClient(application) as client:
        participant, _ = _prepare(
            client, ai={**DEFAULT_AI_CONFIG, "max_turns_per_task": 1}
        )
        task = _start_task(client, participant)
        assert _send(client, participant, task["id"], "Вопрос", "l1").status_code == 200
        blocked = _send(client, participant, task["id"], "Ещё вопрос", "l2")
        assert blocked.status_code == 429
        crisis = _send(client, participant, task["id"], "хочу умереть", "l3")
        assert crisis.status_code == 200
        assert "8-800-2000-122" in crisis.json()["assistantMessage"]
