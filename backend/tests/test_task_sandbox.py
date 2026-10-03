from __future__ import annotations

import json

from fastapi.testclient import TestClient
from task_module_samples import PLUS_ONE

from app.config import Settings
from app.main import create_app

EMPTY_STATE = json.dumps({'public_state': {}, 'private_state': {}})


def auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _client(tmp_path, modules_dir=None) -> TestClient:
    settings = Settings(
        database_url=f'sqlite:///{tmp_path / "sandbox.db"}',
        organizer_code='ORBIT-ADMIN',
        security_secret='test-token-secret-that-is-long',
        code_hmac_secret='test-code-secret-that-is-different',
        task_modules_dir=str(modules_dir) if modules_dir else None,
    )
    return TestClient(create_app(settings))


def _organizer(client: TestClient) -> dict[str, str]:
    return auth(client.post('/api/v1/access/redeem', json={'code': 'ORBIT-ADMIN'}).json()['access_token'])


def _private(task: dict) -> dict:
    return json.loads(task['state'])['private_state']


def test_sandbox_is_for_organizers_only(tmp_path):
    with _client(tmp_path) as client:
        assert client.post('/api/v1/sandbox/tasks', json={'family': 'fold_punch'}).status_code == 401
        assert client.post('/api/v1/task-modules/reload').status_code == 401


def test_sandbox_generates_a_reproducible_task_with_its_reference_answer(tmp_path):
    with _client(tmp_path) as client:
        organizer = _organizer(client)
        first = client.post(
            '/api/v1/sandbox/tasks',
            headers=organizer,
            json={'family': 'geo_probability', 'difficulty': 3, 'seed': 42},
        )
        again = client.post(
            '/api/v1/sandbox/tasks',
            headers=organizer,
            json={'family': 'geo_probability', 'difficulty': 3, 'seed': 42},
        )
        random_seed = client.post(
            '/api/v1/sandbox/tasks', headers=organizer, json={'family': 'geo_probability'}
        )
        unknown = client.post('/api/v1/sandbox/tasks', headers=organizer, json={'family': 'no_such_family'})

        assert first.status_code == 200
        task = first.json()
        assert task == again.json()
        assert (task['family'], task['seed'], task['difficulty']) == ('geo_probability', 42, 3)
        assert task['reference_answer'].startswith('/answer ')
        assert random_seed.json()['seed'] != 42
        assert random_seed.json()['seed'] < 2**53
        assert unknown.status_code == 404

        checked = client.post(
            '/api/v1/sandbox/answers',
            headers=organizer,
            json={'family': 'geo_probability', 'answer': task['reference_answer'], 'state': task['state']},
        ).json()
        assert checked == {'evaluation': checked['evaluation'], 'finalized': True}
        assert checked['evaluation']['correct'] is True


def test_sandbox_plays_an_interactive_task_and_stores_nothing(tmp_path):
    with _client(tmp_path) as client:
        organizer = _organizer(client)
        task = client.post(
            '/api/v1/sandbox/tasks',
            headers=organizer,
            json={'family': 'machine_reach', 'difficulty': 2, 'seed': 7, 'sub_kind': 'lamps_gf2'},
        ).json()
        assert task['public_state']['sub_kind'] == 'lamps_gf2'

        moved = client.post(
            '/api/v1/sandbox/interactions',
            headers=organizer,
            json={
                'family': 'machine_reach',
                'action_type': 'apply_op',
                'op_id': task['public_state']['ops'][0]['id'],
                'state': task['state'],
            },
        )
        assert moved.status_code == 200
        step = moved.json()
        assert step['accepted'] is True
        assert step['public_state']['steps_taken'] == 1
        assert json.loads(step['state'])['public_state'] == step['public_state']

        unsupported = client.post(
            '/api/v1/sandbox/interactions',
            headers=organizer,
            json={'family': 'geo_probability', 'action_type': 'hint', 'state': EMPTY_STATE},
        )
        assert unsupported.status_code == 409
        assert client.get('/api/v1/contests', headers=organizer).json()['items'] == []


def test_task_code_failure_is_explained_to_the_author(tmp_path):
    with _client(tmp_path) as client:
        failed = client.post(
            '/api/v1/sandbox/answers',
            headers=_organizer(client),
            json={'family': 'geo_probability', 'answer': '1/2', 'state': EMPTY_STATE},
        )
    assert failed.status_code == 422
    assert failed.json()['detail']['code'] == 'TASK_CODE_FAILED'
    assert 'KeyError' in failed.json()['detail']['message']


def test_sandbox_state_survives_a_browser_that_cannot_keep_large_integers(tmp_path):
    with _client(tmp_path) as client:
        organizer = _organizer(client)
        task = client.post(
            '/api/v1/sandbox/tasks',
            headers=organizer,
            json={'family': 'geo_zendo', 'difficulty': 3, 'seed': 5},
        ).json()
        private_state = _private(task)
        assert private_state['version_space'] > 2**53

        probe = next(iter(private_state['probe_truth_masks']))
        probed = client.post(
            '/api/v1/sandbox/interactions',
            headers=organizer,
            json={'family': 'geo_zendo', 'action_type': 'probe', 'probe': probe, 'state': task['state']},
        ).json()
        assert probed['accepted'] is True
        assert probed['evaluation']['vs_size_before'] == private_state['version_space'].bit_count()

        for broken in (
            '',
            'not json',
            '[]',
            '{"public_state": {}}',
            '{"public_state": 1, "private_state": {}}',
        ):
            rejected = client.post(
                '/api/v1/sandbox/answers',
                headers=organizer,
                json={'family': 'geo_zendo', 'answer': 'да', 'state': broken},
            )
            assert rejected.status_code == 422
            assert rejected.json()['detail']['code'] == 'SANDBOX_STATE_INVALID'


def test_reload_picks_up_an_edited_module_without_a_restart(tmp_path):
    modules = tmp_path / 'modules'
    modules.mkdir()
    with _client(tmp_path, modules) as client:
        organizer = _organizer(client)
        assert 'plus_one' not in {
            item['key'] for item in client.get('/api/v1/task-families', headers=organizer).json()['items']
        }

        (modules / 'plus_one.py').write_text(PLUS_ONE, encoding='utf-8')
        reloaded = client.post('/api/v1/task-modules/reload', headers=organizer).json()
        assert 'plus_one' in {item['key'] for item in reloaded['items']}
        task = client.post(
            '/api/v1/sandbox/tasks',
            headers=organizer,
            json={'family': 'plus_one', 'seed': 3, 'difficulty': 2},
        ).json()
        assert _private(task) == {'answer': 6}

        (modules / 'plus_one.py').write_text(PLUS_ONE.replace('total + 1}', 'total + 2}'), encoding='utf-8')
        client.post('/api/v1/task-modules/reload', headers=organizer)
        edited = client.post(
            '/api/v1/sandbox/tasks',
            headers=organizer,
            json={'family': 'plus_one', 'seed': 3, 'difficulty': 2},
        ).json()
        assert _private(edited) == {'answer': 7}
