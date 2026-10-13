"""A plugin whose code fails during a contest must not stop the participant's attempt."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from task_module_samples import COUNT_UP, PLUS_ONE

from app.config import Settings
from app.main import create_app
from app.models import AttemptEvent

# Each plugin passes the load check, which generates one task of the first level, and fails later.
FAILS_ON_GENERATION = COUNT_UP.replace(
    'def generate(level, rng):\n',
    'def generate(level, rng):\n    if level >= 3:\n        raise RuntimeError("генерация сломана")\n',
)
FAILS_ON_CHECK = COUNT_UP.replace(
    'def check(answer, variant):\n', 'def check(answer, variant):\n    variant["no such key"]\n'
)
FAILS_ON_MOVE = COUNT_UP.replace(
    'def move(variant, text):\n', 'def move(variant, text):\n    if text == "boom":\n        return 1 / 0\n'
)


def _contest(tmp_path, plugin: str, families: list[dict]):
    modules = tmp_path / 'modules'
    modules.mkdir()
    (modules / 'counting.py').write_text(plugin, encoding='utf-8')
    (modules / 'plus_one.py').write_text(PLUS_ONE, encoding='utf-8')
    settings = Settings(
        database_url=f'sqlite:///{tmp_path / "failures.db"}',
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
        json={'title': 'Сбои', 'duration_minutes': 30, 'task_config': {'families': families}},
    ).json()
    client.post(
        f'/api/v1/contests/{contest["id"]}/enrollments',
        headers=organizer,
        json={'participants': [{'external_ref': 'p1', 'display_name': 'Участник'}]},
    )
    codes = client.post(f'/api/v1/contests/{contest["id"]}/codes', headers=organizer, json={}).json()
    client.post(f'/api/v1/contests/{contest["id"]}/publish', headers=organizer)
    participant_token = client.post('/api/v1/access/redeem', json={'code': codes['items'][0]['code']}).json()
    participant = {'Authorization': f'Bearer {participant_token["access_token"]}'}
    attempt = client.post('/api/v1/participant/attempts/start', headers=participant).json()['attempt']
    return application, client, participant, attempt['id']


def _family(key: str, level: int = 1) -> dict:
    return {'key': key, 'enabled': True, 'weight': 1, 'initial_difficulty': level, 'max_difficulty': level}


def _events(application, attempt_id: str, event_type: str) -> list[dict]:
    with application.state.database.session_factory() as session:
        events = session.scalars(
            select(AttemptEvent)
            .where(AttemptEvent.attempt_id == attempt_id, AttemptEvent.event_type == event_type)
            .order_by(AttemptEvent.sequence)
        ).all()
        return [event.payload for event in events]


def test_participant_gets_another_task_when_a_plugin_cannot_generate_one(tmp_path):
    application, client, participant, attempt_id = _contest(
        tmp_path, FAILS_ON_GENERATION, [_family('count_up', level=3), _family('plus_one')]
    )
    with client:
        families = []
        for step in range(4):
            path = '/api/v1/participant/tasks/current' if step == 0 else '/api/v1/participant/tasks/next'
            opened = (
                client.get(path, headers=participant) if step == 0 else client.post(path, headers=participant)
            )
            assert opened.status_code == 200, opened.text
            task = opened.json()['task']
            families.append(task['family'])
            client.post(f'/api/v1/participant/tasks/{task["id"]}/skip', headers=participant)

    assert families == ['plus_one'] * 4
    failures = _events(application, attempt_id, 'task_generation_failed')
    assert failures, 'the failing plugin was never tried'
    assert {failure['family'] for failure in failures} == {'count_up'}
    assert failures[0]['error'].startswith('RuntimeError: генерация сломана\ncounting.py, строка')


def test_contest_with_nothing_but_a_failing_plugin_says_so_instead_of_crashing(tmp_path):
    application, client, participant, attempt_id = _contest(
        tmp_path, FAILS_ON_GENERATION, [_family('count_up', level=3)]
    )
    with client:
        opened = client.get('/api/v1/participant/tasks/current', headers=participant)

    assert opened.status_code == 503
    assert opened.json()['detail']['code'] == 'TASK_GENERATION_FAILED'
    assert len(_events(application, attempt_id, 'task_generation_failed')) == 1


def test_failed_check_is_reported_and_the_task_can_be_skipped(tmp_path):
    application, client, participant, attempt_id = _contest(tmp_path, FAILS_ON_CHECK, [_family('count_up')])
    with client:
        task = client.get('/api/v1/participant/tasks/current', headers=participant).json()['task']
        answered = client.post(
            f'/api/v1/participant/tasks/{task["id"]}/answer', headers=participant, json={'answer': '4'}
        )
        skipped = client.post(f'/api/v1/participant/tasks/{task["id"]}/skip', headers=participant)
        following = client.post('/api/v1/participant/tasks/next', headers=participant)

    assert answered.status_code == 422
    assert answered.json()['detail']['code'] == 'TASK_CODE_FAILED'
    assert '/skip' in answered.json()['detail']['message']
    assert skipped.status_code == 200
    assert following.json()['task']['ordinal'] == 2
    (failure,) = _events(application, attempt_id, 'task_code_failed')
    assert failure['action'] == 'answer'
    assert failure['error'].startswith("KeyError: 'no such key'\ncounting.py, строка")


def test_failed_move_leaves_the_task_as_it_was(tmp_path):
    application, client, participant, attempt_id = _contest(tmp_path, FAILS_ON_MOVE, [_family('count_up')])
    with client:
        task = client.get('/api/v1/participant/tasks/current', headers=participant).json()['task']
        url = f'/api/v1/participant/tasks/{task["id"]}/interactions'
        broken = client.post(
            url,
            headers=participant,
            json={'action_type': 'apply_op', 'op_id': 'boom', 'client_action_id': 'a1'},
        )
        moved = client.post(
            url,
            headers=participant,
            json={'action_type': 'apply_op', 'op_id': 'plus', 'client_action_id': 'a2'},
        )

    assert broken.status_code == 422
    assert broken.json()['detail']['code'] == 'TASK_CODE_FAILED'
    assert moved.status_code == 200
    assert moved.json()['task']['public_state']['blocks'][0]['items'] == ['Счётчик: 1']
    (failure,) = _events(application, attempt_id, 'task_code_failed')
    assert (failure['action'], failure['error'].splitlines()[0]) == (
        'apply_op',
        'ZeroDivisionError: division by zero',
    )
