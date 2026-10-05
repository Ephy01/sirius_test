"""The JSON protocol between the task editor in a browser and ``sirius_gate``."""

from __future__ import annotations

import json

import pytest
from task_module_samples import PLUS_ONE

from sirius_gate import editor


def _call(op: str, **args) -> dict:
    return json.loads(editor.handle(json.dumps({'op': op, 'args': args})))


@pytest.fixture(autouse=True)
def _empty_editor():
    editor._families.clear()
    yield
    editor._families.clear()


def test_editor_loads_a_text_and_plays_the_task_like_the_api_does():
    catalog = _call('load', source=PLUS_ONE)['result']
    assert [(item['key'], item['title'], item['source']) for item in catalog['items']] == [
        ('plus_one', 'Плюс один', 'module')
    ]

    task = _call('generate', family='plus_one', difficulty=2, seed=3)['result']
    assert (task['seed'], task['generator_version']) == (3, 'plus-one-v1')
    assert task['public_state']['prompt'] == 'Сколько будет 5 + 1?'

    checked = _call('answer', family='plus_one', answer='6', state=task['state'])['result']
    assert checked == {'evaluation': {'correct': True}, 'finalized': True}


def test_text_with_an_error_is_explained_and_leaves_the_open_task_playable():
    _call('load', source=PLUS_ONE)
    task = _call('generate', family='plus_one', seed=3)['result']

    failed = _call('load', source=PLUS_ONE.replace('total = seed % 7', 'total = sed % 7'))

    assert failed['error']['code'] == 'TASK_CODE_FAILED'
    assert "NameError: name 'sed' is not defined" in failed['error']['message']
    assert 'task.py, строка 6, функция generate' in failed['error']['message']
    assert _call('catalog')['result']['items'][0]['key'] == 'plus_one'
    assert _call('answer', family='plus_one', answer='5', state=task['state'])['result']['finalized'] is True


def test_editor_reports_what_it_cannot_do_with_the_codes_of_the_api():
    _call('load', source=PLUS_ONE)
    task = _call('generate', family='plus_one', seed=3)['result']

    unknown = _call('generate', family='no_such_family')
    unsupported = _call('interact', family='plus_one', action_type='hint', state=task['state'])
    damaged = _call('answer', family='plus_one', answer='1', state='{}')

    assert unknown['error']['code'] == 'TASK_FAMILY_UNKNOWN'
    assert unsupported['error']['code'] == 'TASK_INTERACTION_ACTION_NOT_SUPPORTED'
    assert damaged['error']['code'] == 'SANDBOX_STATE_INVALID'


def test_editor_checks_a_family_and_returns_the_table_with_its_rows():
    _call('load', source=PLUS_ONE)

    report = _call('check', family='plus_one', seeds=14)['result']

    assert [level['generated'] for level in report['levels']] == [14] * 5
    assert report['levels'][0]['distinct'] == 7
    assert report['report'].startswith('plus_one (Плюс один), версия plus-one-v1')


def test_state_that_json_cannot_hold_is_reported_as_an_error_in_task_code():
    source = PLUS_ONE.replace('{"answer": total + 1}', '{"answer": float("nan") if seed == 9 else 1}')
    _call('load', source=source)

    failed = _call('generate', family='plus_one', seed=9)

    assert failed['error']['code'] == 'TASK_CODE_FAILED'
    assert 'JSON' in failed['error']['message']
