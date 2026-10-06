"""The plugin interface of the hackathon brief: metadata, task types and their five methods."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from task_module_samples import COUNT_UP

from app.config import Settings
from app.main import create_app
from sirius_gate import sandbox
from sirius_gate.catalog import describe
from sirius_gate.check import check_family
from sirius_gate.loading import load_source


def _family(source: str = COUNT_UP):
    module = load_source(source, name='counting')
    assert module.error is None, module.error
    return module.families[0]


def _act(family, task, **action):
    return sandbox.interact(family, state=task['state'], **action)


def test_plugin_carries_its_metadata_and_three_named_levels():
    entry = describe(_family(), module='counting')

    assert (entry['key'], entry['title'], entry['author'], entry['version']) == (
        'count_up',
        'Счётчик',
        'Команда 7',
        'counting-1.2',
    )
    assert entry['description'] == 'Учебный плагин со счётчиком.'
    assert (entry['min_difficulty'], entry['max_difficulty']) == (1, 3)
    assert entry['level_titles'] == ['простой', 'средний', 'повышенной сложности']
    assert entry['interactive'] is True


def test_only_variants_that_pass_validation_reach_a_participant():
    family = _family()

    targets = {
        sandbox.generate(family, seed=seed, difficulty=3)['public_state']['prompt'] for seed in range(40)
    }

    assert targets <= {f'Доведите счётчик до {target}.' for target in (2, 4, 6, 8)}
    assert len(targets) > 1


def test_validation_that_accepts_nothing_stops_the_plugin_from_loading():
    module = load_source(COUNT_UP.replace('variant["target"] % 2 == 0', 'False'), name='counting')

    assert module.families == ()
    assert 'за 200 попыток generate не дала варианта, который принимает validate' in module.error


def test_a_level_the_plugin_does_not_have_is_refused():
    with pytest.raises(sandbox.LevelNotSupported, match='от 1 до 3'):
        sandbox.generate(_family(), seed=1, difficulty=4)


def test_moves_change_the_view_and_undo_and_reset_come_for_free():
    family = _family()
    task = sandbox.generate(family, seed=4, difficulty=1)
    assert task['public_state']['commands'] == ['done', 'op', 'undo', 'reset']
    assert task['reference_commands'] == ['/op plus', '/op plus']

    refused = _act(family, task, action_type='apply_op', op_id='minus')
    assert (refused['accepted'], refused['message']) == (False, 'Можно только прибавлять.')

    once = _act(family, task, action_type='apply_op', op_id='plus')
    twice = _act(family, once, action_type='apply_op', op_id='plus')
    assert (twice['accepted'], twice['message']) == (True, 'Прибавили один.')
    assert twice['public_state']['blocks'][0]['items'] == ['Счётчик: 2']
    assert sandbox.answer(family, answer='done', state=twice['state'])['evaluation'] == {'correct': True}
    assert twice['reference_commands'] == []

    undone = _act(family, twice, action_type='undo')
    assert undone['public_state']['blocks'][0]['items'] == ['Счётчик: 1']
    assert sandbox.answer(family, answer='done', state=undone['state']) == {
        'evaluation': {
            'correct': False,
            'should_finalize': False,
            'feedback': 'Счётчик ещё не дошёл до цели.',
        },
        'finalized': False,
    }

    cleared = _act(family, undone, action_type='reset')
    assert cleared['public_state'] == task['public_state']
    assert _act(family, cleared, action_type='undo')['accepted'] is False


def test_language_model_is_told_about_the_scene_and_never_about_the_variant():
    family = _family()
    assert family.ai_context is None

    narrowed = _family(
        COUNT_UP.replace(
            '            move=move,',
            '            move=move,\n            model_context=lambda scene: {"statement": scene["prompt"]},',
        )
    )
    scene = sandbox.generate(narrowed, seed=4)['public_state']

    assert narrowed.ai_context(scene) == {'statement': scene['prompt']}


@pytest.mark.parametrize(
    ('change', 'expected'),
    [
        (('name="counting"', 'name="Счёт"'), 'имя плагина'),
        (('version="1.2"', 'version=""'), 'версия плагина'),
        (('author="Команда 7"', 'author=""'), 'автор'),
        (('task_types=[', 'api=99, task_types=['), 'версии интерфейса 99'),
        (('key="count_up"', 'key="geo zendo"'), 'ключ типа задачи'),
        (('return variant["target"] % 2 == 0', 'return 1'), 'validate должна вернуть True или False'),
        (
            ('    return blocks.scene(', '    return dict(prompt="?") or blocks.scene('),
            'view должна вернуть blocks.scene',
        ),
        (
            ('return {"target": rng.randint(2, LIMITS[level]), "count": 0}', 'return 5'),
            'generate должна вернуть словарь',
        ),
    ],
)
def test_plugin_that_breaks_the_interface_is_explained_to_its_author(change, expected):
    module = load_source(COUNT_UP.replace(*change), name='counting')

    assert module.families == ()
    assert expected in module.error


def test_plugin_passes_the_module_check_on_its_three_levels():
    levels = check_family(_family(), seeds=12)

    assert [
        (level.difficulty, level.generated, level.reference_accepted, level.problems) for level in levels
    ] == [(1, 12, 12, []), (2, 12, 12, []), (3, 12, 12, [])]


def test_contest_never_asks_a_plugin_for_a_level_it_does_not_have(tmp_path):
    modules = tmp_path / 'modules'
    modules.mkdir()
    (modules / 'counting.py').write_text(COUNT_UP, encoding='utf-8')
    settings = Settings(
        database_url=f'sqlite:///{tmp_path / "plugin.db"}',
        organizer_code='ORBIT-ADMIN',
        security_secret='test-token-secret-that-is-long',
        code_hmac_secret='test-code-secret-that-is-different',
        task_modules_dir=str(modules),
    )
    with TestClient(create_app(settings)) as client:
        token = client.post('/api/v1/access/redeem', json={'code': 'ORBIT-ADMIN'}).json()['access_token']
        organizer = {'Authorization': f'Bearer {token}'}
        family = {
            'key': 'count_up',
            'enabled': True,
            'weight': 1,
            'initial_difficulty': 5,
            'max_difficulty': 5,
        }
        contest = client.post(
            '/api/v1/contests',
            headers=organizer,
            json={'title': 'Плагин', 'duration_minutes': 30, 'task_config': {'families': [family]}},
        ).json()
        client.post(
            f'/api/v1/contests/{contest["id"]}/enrollments',
            headers=organizer,
            json={'participants': [{'external_ref': 'p1', 'display_name': 'Участник'}]},
        )
        code = client.post(f'/api/v1/contests/{contest["id"]}/codes', headers=organizer, json={}).json()[
            'items'
        ][0]['code']
        client.post(f'/api/v1/contests/{contest["id"]}/publish', headers=organizer)
        participant = {
            'Authorization': 'Bearer '
            + client.post('/api/v1/access/redeem', json={'code': code}).json()['access_token']
        }
        client.post('/api/v1/participant/attempts/start', headers=participant)

        opened = client.get('/api/v1/participant/tasks/current', headers=participant)

    assert opened.status_code == 200, opened.text
    task = opened.json()['task']
    assert (task['family'], task['difficulty']) == ('count_up', 3)
