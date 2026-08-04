from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_production_disables_schema_creation_and_api_documentation(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "production.db"
    settings = Settings(
        environment="production",
        database_url=f"sqlite:///{database_path}",
        organizer_code="test-admin",
        security_secret="test-security-secret",
        code_hmac_secret="test-code-secret",
    )
    app = create_app(settings)

    def fail_if_called() -> None:
        raise AssertionError("production startup must not call create_all")

    monkeypatch.setattr(app.state.database, "create_schema", fail_if_called)

    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
