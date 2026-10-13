"""Dragging a shape of a drawing: the drop reaches the plugin as a logged move."""

from __future__ import annotations

from plugin_contest import events, family, open_contest
from task_module_samples import MIDPOINT

from sirius_gate import sandbox
from sirius_gate.check import check_family
from sirius_gate.loading import load_source


def _family():
    module = load_source(MIDPOINT, name='midpoint')
    assert module.error is None, module.error
    return module.families[0]


def _drop(family, task, text):
    return sandbox.interact(family, action_type='apply_op', op_id=text, state=task['state'])


def _point(task, label):
    shapes = task['public_state']['blocks'][0]['shapes']
    return next(shape for shape in shapes if shape.get('label') == label)


def test_draggable_shape_is_marked_and_the_task_explains_the_typed_form():
    task = sandbox.generate(_family(), seed=3, difficulty=2)

    assert (_point(task, 'M')['drag'], _point(task, 'A')['drag']) == ('M', None)
    assert task['public_state']['commands'] == ['done', 'op', 'undo', 'reset']
    assert task['public_state']['help'][0].startswith('/op drag:<имя>:<x>:<y>')


def test_drop_lands_on_the_grid_and_is_passed_to_the_plugin():
    family = _family()
    task = sandbox.generate(family, seed=3, difficulty=2)

    moved = _drop(family, task, 'drag:M:3.4:2.6')

    assert (moved['accepted'], moved['message']) == (True, 'Точка M теперь в (3, 3).')
    assert (_point(moved, 'M')['x'], _point(moved, 'M')['y']) == (3, 3)


def test_drop_outside_the_drawing_or_of_an_unknown_shape_is_refused():
    family = _family()
    task = sandbox.generate(family, seed=3, difficulty=2)

    outside = _drop(family, task, 'drag:M:40:2')
    fixed = _drop(family, task, 'drag:A:3:3')
    garbled = _drop(family, task, 'drag:M:три:3')
    endless = _drop(family, task, 'drag:M:inf:3')
    refused = _drop(family, task, f'drag:M:{_point(task, "A")["x"]}:1')
    typed = _drop(family, task, 'press:1:1')

    assert (outside['accepted'], outside['message']) == (False, 'Объект нельзя вынести за пределы рисунка.')
    assert fixed['message'] == 'На рисунке нет объекта A, который можно переносить.'
    assert garbled['message'] == endless['message'] == 'Перенос записывается так: /op drag:<имя>:<x>:<y>.'
    assert refused['message'] == 'Точка M не может совпадать с A.'
    assert typed['message'] == 'В этой задаче объекты только переносятся.'
    assert all(
        result['public_state'] == task['public_state'] for result in (outside, fixed, garbled, refused)
    )


def test_drops_can_be_undone_and_the_reference_solution_is_a_drop():
    family = _family()
    task = sandbox.generate(family, seed=3, difficulty=2)
    first = _drop(family, task, 'drag:M:2:2')
    second = _drop(family, first, 'drag:M:6:4')

    undone = sandbox.interact(family, action_type='undo', state=second['state'])

    assert (_point(undone, 'M')['x'], _point(undone, 'M')['y']) == (2, 2)
    solved = _drop(family, undone, task['reference_commands'][0].removeprefix('/op '))
    assert sandbox.answer(family, answer='done', state=solved['state'])['evaluation'] == {'correct': True}
    levels = check_family(family, seeds=8)
    assert [(level.generated, level.reference_accepted, level.problems) for level in levels] == [
        (8, 8, [])
    ] * 5


def test_drop_in_a_contest_is_logged_as_a_move_of_the_participant(tmp_path):
    application, client, participant, attempt_id = open_contest(
        tmp_path, {'midpoint': MIDPOINT}, [family('midpoint', level=2)]
    )
    with client:
        task = client.get('/api/v1/participant/tasks/current', headers=participant).json()['task']
        dropped = client.post(
            f'/api/v1/participant/tasks/{task["id"]}/interactions',
            headers=participant,
            json={'action_type': 'apply_op', 'op_id': 'drag:M:3.4:2.6', 'client_action_id': 'drop-1'},
        )

    assert dropped.status_code == 200, dropped.text
    assert dropped.json()['message'] == 'Точка M теперь в (3, 3).'
    (submitted,) = events(application, attempt_id, 'task_interaction_submitted')
    assert (submitted['action_type'], submitted['op_id']) == ('apply_op', 'drag:M:3.4:2.6')
    (resolved,) = events(application, attempt_id, 'task_interaction_resolved')
    assert (resolved['accepted'], resolved['reason']) == (True, 'accepted')
    assert resolved['before_state_hash'] != resolved['after_state_hash']
