from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from task_module_samples import PLUS_ONE

from app.config import Settings
from app.main import create_app
from app.tasks import FAMILIES, generate_task
from app.tasks.modules import load_task_modules
from app.tasks.registry import BUILTIN_KEYS


def _write(directory: Path, name: str, source: str) -> None:
    target = directory / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding='utf-8')


def auth(token: str) -> dict[str, str]:
    return {'Authorization': f'Bearer {token}'}


def test_module_file_adds_a_family_and_unloading_removes_it(tmp_path):
    _write(tmp_path, 'plus_one.py', PLUS_ONE)

    loaded = load_task_modules(str(tmp_path))

    assert [(module.name, [family.key for family in module.families], module.error) for module in loaded] == [
        ('plus_one', ['plus_one'], None)
    ]
    task = generate_task(family='plus_one', generator_version='plus-one-v1', seed=3, difficulty=2)
    assert task.public_state['kind'] == 'blocks'
    assert task.private_state == {'answer': 6}

    assert load_task_modules(None) == []
    assert set(FAMILIES) == BUILTIN_KEYS


def test_module_folder_can_import_its_own_files(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, 'dont_write_bytecode', False)
    _write(tmp_path, 'shared/helper.py', "TITLE = 'Из соседнего файла'\n")
    _write(
        tmp_path,
        'shared/task.py',
        PLUS_ONE.replace('from sirius_gate import', 'from .helper import TITLE\nfrom sirius_gate import')
        .replace('title="Плюс один"', 'title=TITLE')
        .replace('key="plus_one"', 'key="shared_one"'),
    )

    loaded = load_task_modules(str(tmp_path))

    assert loaded[0].error is None
    assert FAMILIES['shared_one'].card.title == 'Из соседнего файла'
    assert not list(tmp_path.rglob('__pycache__')), 'cached bytecode would hide a quick edit of the module'
    assert sys.dont_write_bytecode is False


@pytest.mark.parametrize(
    ('source', 'expected'),
    [
        ('def broken(:\n', 'SyntaxError'),
        ('VALUE = 1\n', 'must define FAMILY'),
        (PLUS_ONE.replace('key="plus_one"', 'key="geo_zendo"'), 'already taken by the platform'),
        (PLUS_ONE.replace('key="plus_one"', 'key="Плюс"'), 'lowercase latin'),
        (PLUS_ONE + 'API = 99\n', 'interface version 99'),
        (
            PLUS_ONE.replace('total = seed % 7 + difficulty', 'import random\n    total = random.random()'),
            'same task for the same seed',
        ),
        (PLUS_ONE.replace('return public, {"answer": total + 1}', 'return public'), 'two dicts'),
    ],
)
def test_broken_module_is_reported_and_does_not_touch_the_platform(tmp_path, source, expected):
    _write(tmp_path, 'broken.py', source)
    _write(tmp_path, 'plus_one.py', PLUS_ONE)

    loaded = {module.name: module for module in load_task_modules(str(tmp_path))}

    assert expected in loaded['broken'].error
    assert loaded['broken'].families == ()
    assert loaded['plus_one'].error is None
    assert set(FAMILIES) == BUILTIN_KEYS | {'plus_one'}


def test_two_modules_cannot_share_a_family_key(tmp_path):
    _write(tmp_path, 'a_first.py', PLUS_ONE)
    _write(tmp_path, 'b_second.py', PLUS_ONE)

    first, second = load_task_modules(str(tmp_path))

    assert first.error is None
    assert 'already taken by a_first' in second.error


def test_module_family_runs_through_a_contest(tmp_path):
    _write(tmp_path / 'modules', 'plus_one.py', PLUS_ONE)
    settings = Settings(
        database_url=f'sqlite:///{tmp_path / "modules.db"}',
        organizer_code='ORBIT-ADMIN',
        security_secret='test-token-secret-that-is-long',
        code_hmac_secret='test-code-secret-that-is-different',
        task_modules_dir=str(tmp_path / 'modules'),
    )
    application = create_app(settings)
    with TestClient(application) as client:
        organizer = client.post('/api/v1/access/redeem', json={'code': 'ORBIT-ADMIN'}).json()['access_token']
        contest = client.post(
            '/api/v1/contests',
            headers=auth(organizer),
            json={'title': 'Модуль', 'task_config': {'families': ['plus_one']}},
        )
        assert contest.status_code == 201
        contest_id = contest.json()['id']
        client.post(
            f'/api/v1/contests/{contest_id}/enrollments',
            headers=auth(organizer),
            json={'participants': [{'external_ref': 'm-1', 'display_name': 'Участник'}]},
        )
        code = client.post(f'/api/v1/contests/{contest_id}/codes', headers=auth(organizer), json={}).json()[
            'items'
        ][0]['code']
        client.post(f'/api/v1/contests/{contest_id}/publish', headers=auth(organizer))
        participant = client.post('/api/v1/access/redeem', json={'code': code}).json()['access_token']
        client.post('/api/v1/participant/attempts/start', headers=auth(participant))

        task = client.get('/api/v1/participant/tasks/current', headers=auth(participant)).json()['task']
        assert task['family'] == 'plus_one'
        assert task['generator_version'] == 'plus-one-v1'
        assert task['public_state']['kind'] == 'blocks'
        assert 'answer' not in str(task['public_state'])

        number = int(task['public_state']['prompt'].split()[2]) + 1
        answered = client.post(
            f'/api/v1/participant/tasks/{task["id"]}/answer',
            headers=auth(participant),
            json={'answer': str(number)},
        )
        assert answered.status_code == 200
        assert answered.json()['task']['status'] == 'answered'


def test_assistant_sees_the_blocks_of_a_module_task_without_click_commands(tmp_path):
    from app.ai import build_task_context
    from app.models import TaskInstance
    from sirius_gate import blocks

    public = blocks.scene(
        'Нажмите клетку.',
        [blocks.grid([[blocks.cell('●', tone='accent', command='/op press:0:0'), blocks.cell()]])],
        commands=['op'],
    )
    task = TaskInstance(
        id='t',
        attempt_id='a',
        ordinal=1,
        family='unknown_module_family',
        generator_version='v1',
        seed=1,
        difficulty=1,
        public_state=public,
        private_state={'secret': 42},
    )

    context = build_task_context(task, [])

    assert context.payload['visibleState'] == {
        'blocks': [
            {
                'type': 'grid',
                'caption': None,
                'cells': [[{'text': '●', 'tone': 'accent'}, {'text': '', 'tone': 'plain'}]],
            }
        ],
        'commands': ['op'],
    }
    assert 'secret' not in context.canonical_json
    assert '/op press' not in context.canonical_json


def test_block_builders_reject_what_the_client_would_not_draw():
    from sirius_gate import blocks

    with pytest.raises(ValueError, match='должна начинаться'):
        blocks.cell('1', command='press 1')
    with pytest.raises(ValueError, match='должна начинаться'):
        blocks.button('Нажать', 'нажми')
    with pytest.raises(ValueError, match='оттенок'):
        blocks.cell('1', tone='red')
    with pytest.raises(ValueError, match='прямоугольником'):
        blocks.grid([[1, 2], [3]])
    with pytest.raises(ValueError, match='столько же значений'):
        blocks.table(['a', 'b'], [[1]])
    with pytest.raises(ValueError, match='команды задачи'):
        blocks.scene('q', [], commands=['fly'])
    assert blocks.button('Готово', 'done') == {'label': 'Готово', 'command': 'done'}
    assert blocks.cell(command=' /op x ')['command'] == '/op x'
