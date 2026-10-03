from __future__ import annotations

from fastapi.testclient import TestClient
from task_module_samples import PLUS_ONE

from app.config import Settings
from app.main import create_app


def auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def _client(tmp_path, modules_dir=None) -> TestClient:
    settings = Settings(
        database_url=f'sqlite:///{tmp_path / "catalog.db"}',
        organizer_code='ORBIT-ADMIN',
        security_secret='test-token-secret-that-is-long',
        code_hmac_secret='test-code-secret-that-is-different',
        task_modules_dir=str(modules_dir) if modules_dir else None,
    )
    return TestClient(create_app(settings))


def test_catalog_describes_builtin_families_for_the_builder(tmp_path):
    with _client(tmp_path) as client:
        assert client.get('/api/v1/task-families').status_code == 401
        organizer = client.post('/api/v1/access/redeem', json={'code': 'ORBIT-ADMIN'}).json()['access_token']
        catalog = client.get('/api/v1/task-families', headers=auth(organizer)).json()

    items = {item['key']: item for item in catalog['items']}
    assert catalog['problems'] == []
    assert len(items) == 12
    assert all(item['source'] == 'builtin' and item['module'] is None for item in items.values())
    assert all(item['title'] != item['key'] and item['description'] for item in items.values())
    assert sum(item['default_weight'] for item in items.values() if item['listed']) == 96
    assert {key for key, item in items.items() if not item['listed']} == {'dice_chess', 'classic_math'}
    assert items['classic_math']['scripted_only'] is True
    assert [variant['title'] for variant in items['classic_math']['variants']] == [
        'Рассадка в баре',
        'Парадокс долей',
    ]
    assert items['machine_reach']['interactive'] is True
    assert items['geo_probability']['interactive'] is False
    assert (items['geo_zendo']['min_difficulty'], items['geo_zendo']['max_difficulty']) == (1, 5)


def test_catalog_lists_module_families_and_load_problems(tmp_path):
    modules = tmp_path / 'modules'
    modules.mkdir()
    (modules / 'plus_one.py').write_text(PLUS_ONE, encoding='utf-8')
    (modules / 'broken.py').write_text('VALUE = 1\n', encoding='utf-8')

    with _client(tmp_path, modules) as client:
        organizer = client.post('/api/v1/access/redeem', json={'code': 'ORBIT-ADMIN'}).json()['access_token']
        catalog = client.get('/api/v1/task-families', headers=auth(organizer)).json()

    item = next(item for item in catalog['items'] if item['key'] == 'plus_one')
    assert item == {
        'key': 'plus_one',
        'title': 'Плюс один',
        'description': 'Учебный модуль.',
        'version': 'plus-one-v1',
        'source': 'module',
        'module': 'plus_one',
        'listed': True,
        'scripted_only': False,
        'interactive': False,
        'default_weight': 10,
        'default_skin': None,
        'min_difficulty': 1,
        'max_difficulty': 5,
        'variants': [],
    }
    assert [problem['module'] for problem in catalog['problems']] == ['broken']
    assert 'must define FAMILY' in catalog['problems'][0]['error']
