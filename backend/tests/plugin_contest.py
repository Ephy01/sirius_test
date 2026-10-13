"""A contest with plugins from a temporary folder, for tests that follow a participant."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import AttemptEvent


def open_contest(tmp_path, plugins: dict[str, str], families: list[dict]):
    """Start an attempt in a contest of the given families. Returns the app, the client, the headers and the attempt id."""

    modules = tmp_path / 'modules'
    modules.mkdir()
    for name, source in plugins.items():
        (modules / f'{name}.py').write_text(source, encoding='utf-8')
    settings = Settings(
        database_url=f'sqlite:///{tmp_path / "contest.db"}',
        organizer_code='ORBIT-ADMIN',
        security_secret='test-token-secret-that-is-long',
        code_hmac_secret='test-code-secret-that-is-different',
        task_modules_dir=str(modules),
    )
    application = create_app(settings)
    client = TestClient(application)
    client.__enter__()
    token = client.post('/api/v1/access/redeem', json={'code': 'ORBIT-ADMIN'}).json()['access_token']
    organizer = {'Authorization': f'Bearer {token}'}
    contest = client.post(
        '/api/v1/contests',
        headers=organizer,
        json={'title': 'Плагины', 'duration_minutes': 30, 'task_config': {'families': families}},
    ).json()
    client.post(
        f'/api/v1/contests/{contest["id"]}/enrollments',
        headers=organizer,
        json={'participants': [{'external_ref': 'p1', 'display_name': 'Участник'}]},
    )
    codes = client.post(f'/api/v1/contests/{contest["id"]}/codes', headers=organizer, json={}).json()
    client.post(f'/api/v1/contests/{contest["id"]}/publish', headers=organizer)
    redeemed = client.post('/api/v1/access/redeem', json={'code': codes['items'][0]['code']}).json()
    participant = {'Authorization': f'Bearer {redeemed["access_token"]}'}
    attempt = client.post('/api/v1/participant/attempts/start', headers=participant).json()['attempt']
    return application, client, participant, attempt['id']


def family(key: str, level: int = 1) -> dict:
    return {'key': key, 'enabled': True, 'weight': 1, 'initial_difficulty': level, 'max_difficulty': level}


def events(application, attempt_id: str, event_type: str) -> list[dict]:
    with application.state.database.session_factory() as session:
        found = session.scalars(
            select(AttemptEvent)
            .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.event_type == event_type)
            .order_by(AttemptEvent.sequence)
        ).all()
        return [event.payload for event in found]
