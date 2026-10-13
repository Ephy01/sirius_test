"""A plugin whose code fails during a contest must not stop the participant's attempt."""

from __future__ import annotations

from plugin_contest import events, family, open_contest
from task_module_samples import COUNT_UP, PLUS_ONE

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


def test_participant_gets_another_task_when_a_plugin_cannot_generate_one(tmp_path):
    application, client, participant, attempt_id = open_contest(
        tmp_path,
        {'counting': FAILS_ON_GENERATION, 'plus_one': PLUS_ONE},
        [family('count_up', level=3), family('plus_one')],
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
    failures = events(application, attempt_id, 'task_generation_failed')
    assert failures, 'the failing plugin was never tried'
    assert {failure['family'] for failure in failures} == {'count_up'}
    assert failures[0]['error'].startswith('RuntimeError: генерация сломана\ncounting.py, строка')


def test_contest_with_nothing_but_a_failing_plugin_says_so_instead_of_crashing(tmp_path):
    application, client, participant, attempt_id = open_contest(
        tmp_path, {'counting': FAILS_ON_GENERATION}, [family('count_up', level=3)]
    )
    with client:
        opened = client.get('/api/v1/participant/tasks/current', headers=participant)

    assert opened.status_code == 503
    assert opened.json()['detail']['code'] == 'TASK_GENERATION_FAILED'
    assert len(events(application, attempt_id, 'task_generation_failed')) == 1


def test_failed_check_is_reported_and_the_task_can_be_skipped(tmp_path):
    application, client, participant, attempt_id = open_contest(
        tmp_path, {'counting': FAILS_ON_CHECK}, [family('count_up')]
    )
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
    (failure,) = events(application, attempt_id, 'task_code_failed')
    assert failure['action'] == 'answer'
    assert failure['error'].startswith("KeyError: 'no such key'\ncounting.py, строка")


def test_failed_move_leaves_the_task_as_it_was(tmp_path):
    application, client, participant, attempt_id = open_contest(
        tmp_path, {'counting': FAILS_ON_MOVE}, [family('count_up')]
    )
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
    (failure,) = events(application, attempt_id, 'task_code_failed')
    assert (failure['action'], failure['error'].splitlines()[0]) == (
        'apply_op',
        'ZeroDivisionError: division by zero',
    )
