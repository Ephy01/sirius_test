from __future__ import annotations

from fastapi.testclient import TestClient

from app.ai import FakeAssistantProvider
from app.config import Settings
from app.main import create_app


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_organizer_can_download_ai_processed_markdown(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'summary.db'}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
        ai_enabled=True,
        yandex_ai_model_uri="gpt://test-folder/aliceai-llm-flash",
    )
    application = create_app(settings)
    fake = FakeAssistantProvider(
        reply="# Краткое резюме\n\nУчастник ещё не начал попытку."
    )
    application.state.ai_provider = fake
    with TestClient(application) as client:
        organizer = client.post(
            "/api/v1/access/redeem",
            json={"code": "ORBIT-ADMIN"},
        ).json()["access_token"]
        contest = client.post(
            "/api/v1/contests",
            headers=auth(organizer),
            json={
                "title": "Пилот",
                "task_config": {"families": ["chess_coverage"]},
            },
        ).json()
        enrollment = client.post(
            f"/api/v1/contests/{contest['id']}/enrollments",
            headers=auth(organizer),
            json={
                "participants": [
                    {"external_ref": "pilot-01", "display_name": "Участник 1"}
                ]
            },
        ).json()["items"][0]
        response = client.get(
            f"/api/v1/contests/{contest['id']}/enrollments/"
            f"{enrollment['id']}/telemetry/summary",
            headers=auth(organizer),
        )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert ".md" in response.headers["content-disposition"]
    assert "# Краткое резюме" in response.text
    assert len(fake.requests) == 1
    request = fake.requests[0]
    assert "SIRIUS GATE PARTICIPANT TELEMETRY" in request.context_text
    assert "participant_display_name: Участник 1" in request.context_text
    assert "Не давай рекомендацию о" in request.system_prompt
