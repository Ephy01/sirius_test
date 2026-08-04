from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import TaskInstance


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def settings(database_path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{database_path}",
        organizer_code="ORBIT-ADMIN",
        security_secret="test-token-secret-that-is-long",
        code_hmac_secret="test-code-secret-that-is-different",
    )


def prepare_participant(
    client: TestClient,
    *,
    families: list[dict],
    scripted_tasks: list[dict] | None = None,
) -> str:
    organizer = client.post(
        "/api/v1/access/redeem",
        json={"code": "ORBIT-ADMIN"},
    ).json()["access_token"]
    task_config: dict = {"families": families}
    if scripted_tasks is not None:
        task_config["scripted_tasks"] = scripted_tasks
    contest_response = client.post(
        "/api/v1/contests",
        headers=auth(organizer),
        json={
            "title": "Проверка маршрута после пропуска",
            "environment_key": "mixed",
            "task_config": task_config,
        },
    )
    assert contest_response.status_code == 201, contest_response.text
    contest = contest_response.json()
    enrollment_response = client.post(
        f"/api/v1/contests/{contest['id']}/enrollments",
        headers=auth(organizer),
        json={
            "participants": [
                {
                    "external_ref": f"skip-{contest['id']}",
                    "display_name": "Участник",
                }
            ]
        },
    )
    assert enrollment_response.status_code == 201
    code_response = client.post(
        f"/api/v1/contests/{contest['id']}/codes",
        headers=auth(organizer),
        json={},
    )
    assert code_response.status_code == 200
    code = code_response.json()["items"][0]["code"]
    publish_response = client.post(
        f"/api/v1/contests/{contest['id']}/publish",
        headers=auth(organizer),
    )
    assert publish_response.status_code == 200
    redeem_response = client.post(
        "/api/v1/access/redeem",
        json={"code": code},
    )
    assert redeem_response.status_code == 200
    return redeem_response.json()["access_token"]


def start_and_get_task(client: TestClient, participant: str) -> dict:
    started = client.post(
        "/api/v1/participant/attempts/start",
        headers=auth(participant),
    )
    assert started.status_code == 200
    current = client.get(
        "/api/v1/participant/tasks/current",
        headers=auth(participant),
    )
    assert current.status_code == 200
    return current.json()["task"]


def skip_and_get_next(
    client: TestClient,
    participant: str,
    task: dict,
) -> dict:
    skipped = client.post(
        f"/api/v1/participant/tasks/{task['id']}/skip",
        headers=auth(participant),
    )
    assert skipped.status_code == 200
    next_response = client.post(
        "/api/v1/participant/tasks/next",
        headers=auth(participant),
    )
    assert next_response.status_code == 200
    assert next_response.json()["created"] is True
    return next_response.json()["task"]


def test_non_adaptive_skip_rotates_between_enabled_families(tmp_path) -> None:
    application = create_app(settings(tmp_path / "non-adaptive-skip.db"))
    with TestClient(application) as client:
        participant = prepare_participant(
            client,
            families=[
                {"family": "dice_chess", "weight": 1},
                {"family": "machine_reach", "weight": 1},
            ],
        )
        first = start_and_get_task(client, participant)
        second = skip_and_get_next(client, participant, first)
        third = skip_and_get_next(client, participant, second)

        assert second["family"] != first["family"]
        assert third["family"] != second["family"]
        assert [first["ordinal"], second["ordinal"], third["ordinal"]] == [1, 2, 3]


def test_skip_with_one_family_generates_a_fresh_variant(tmp_path) -> None:
    application = create_app(settings(tmp_path / "one-family-skip.db"))
    with TestClient(application) as client:
        participant = prepare_participant(
            client,
            families=[{"family": "dice_chess", "weight": 1}],
        )
        first = start_and_get_task(client, participant)
        second = skip_and_get_next(client, participant, first)

        assert second["family"] == first["family"]
        assert second["id"] != first["id"]
        assert second["ordinal"] == 2
        with application.state.database.session_factory() as session:
            first_stored = session.get(TaskInstance, first["id"])
            second_stored = session.get(TaskInstance, second["id"])
            assert first_stored is not None
            assert second_stored is not None
            assert second_stored.seed != first_stored.seed


def test_scripted_position_has_priority_after_skip(tmp_path) -> None:
    application = create_app(settings(tmp_path / "script-after-skip.db"))
    with TestClient(application) as client:
        participant = prepare_participant(
            client,
            families=[
                {"family": "dice_chess", "weight": 1},
                {"family": "machine_reach", "weight": 1},
            ],
            scripted_tasks=[
                {
                    "family": "classic_math",
                    "sub_kind": "share_paradox",
                    "position": 2,
                }
            ],
        )
        first = start_and_get_task(client, participant)
        scripted = skip_and_get_next(client, participant, first)

        assert scripted["ordinal"] == 2
        assert scripted["family"] == "classic_math"
        assert scripted["public_state"]["sub_kind"] == "share_paradox"
