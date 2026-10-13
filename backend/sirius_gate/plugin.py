"""A plugin: task types written against the interface of the hackathon brief.

A plugin file defines ``PLUGIN = Plugin(...)`` with a name, a version, an author,
a description and task types. A task type tells the platform five things: how to
generate a variant for a level, how to validate it, how to check an answer, how
to show the variant and what the language model is told about it.

Each task type becomes a ``TaskFamily``, so plugins and built-in families run
through the same core.
"""

from __future__ import annotations

import math
import random
import re
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from typing import Any

from . import blocks
from .errors import PluginError
from .family import API, FamilyCard, State, TaskFamily, Transition, required_text

GENERATION_TRIES = 200
NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]{2,39}')
VERSION_PATTERN = re.compile(r'[0-9A-Za-z][0-9A-Za-z._-]{0,19}')
MOVE_COMMANDS = ('op', 'undo', 'reset')
MOVE_HELP = ('/undo — отменить последний ход', '/reset — вернуть начальное состояние')
DROP = 'drag:'
DROP_HELP = '/op drag:<имя>:<x>:<y> — перенести объект в точку с этими координатами'


class Rejected(Exception):
    """Raised by ``move`` to refuse a move; the text is shown to the participant."""


class NotYet(Exception):
    """Raised by ``check`` when the answer cannot be judged yet; the task stays open."""


@dataclass(frozen=True)
class TaskType:
    """One type of task inside a plugin.

    ``generate(level, rng)`` returns the variant for a level from 1 (the simplest) to 5:
    a dict with everything that defines the task, the answer included. ``validate(variant)`` says whether the variant may
    be given to a participant. ``check(answer, variant)`` says whether the answer is
    right, or raises ``NotYet`` to keep the task open. ``view(variant)`` returns
    ``blocks.scene(...)``, which is all a participant
    sees. ``model_context(scene)`` narrows what the language model is told, it gets
    the scene and never the variant.

    ``move(variant, text)`` makes the task interactive: it handles ``/op <text>`` and
    returns the changed variant, optionally with a message. ``drag(variant, name, x, y)``
    does the same when the participant drags a shape of the drawing to a new place.
    Undo and reset then work without more code.
    """

    key: str
    title: str
    generate: Callable[[int, random.Random], State]
    check: Callable[[str, State], Any]
    view: Callable[[State], State]
    description: str = ''
    validate: Callable[[State], bool] | None = None
    solution: Callable[[State], Any] | None = None
    model_context: Callable[[State], State] | None = None
    move: Callable[[State, str], Any] | None = None
    drag: Callable[[State, str, float, float], Any] | None = None

    @property
    def interactive(self) -> bool:
        return self.move is not None or self.drag is not None


@dataclass(frozen=True)
class Plugin:
    name: str
    version: str
    author: str
    description: str
    task_types: Sequence[TaskType]
    api: int = API

    def families(self) -> tuple[TaskFamily, ...]:
        """The task types as records the core runs."""

        self._check_metadata()
        return tuple(_family(self, task) for task in self.task_types)

    def _check_metadata(self) -> None:
        if not isinstance(self.name, str) or not NAME_PATTERN.fullmatch(self.name):
            raise PluginError(
                'имя плагина пишется строчными латинскими буквами, цифрами и знаком "_", от 3 до 40 знаков'
            )
        if not isinstance(self.version, str) or not VERSION_PATTERN.fullmatch(self.version):
            raise PluginError('версия плагина пишется латинскими буквами, цифрами и точками, например "1.0"')
        if not all(isinstance(text, str) and text.strip() for text in (self.author, self.description)):
            raise PluginError('у плагина должны быть автор (author) и описание (description)')
        if self.api != API:
            raise PluginError(
                f'плагин написан для версии интерфейса {self.api}, платформа предоставляет {API}'
            )
        types = list(self.task_types)
        if not types or any(not isinstance(task, TaskType) for task in types):
            raise PluginError('в task_types должен быть хотя бы один тип задачи, созданный через TaskType')


def _scene(task: TaskType, variant: State) -> State:
    scene = task.view(deepcopy(variant))
    if not isinstance(scene, dict) or scene.get('kind') != blocks.KIND:
        raise PluginError('view должна вернуть blocks.scene(...)')
    if not task.interactive:
        return scene
    commands = list(scene.get('commands') or [])
    lines = list(scene.get('help') or [])
    offered = (DROP_HELP, *MOVE_HELP) if task.drag is not None else MOVE_HELP
    return {
        **scene,
        'commands': commands + [name for name in MOVE_COMMANDS if name not in commands],
        'help': lines + [line for line in offered if not any(line.split()[0] in known for known in lines)],
    }


def _generate(task: TaskType, seed: int, difficulty: int, context: State) -> tuple[State, State]:
    rng = random.Random(seed)
    for _ in range(GENERATION_TRIES):
        variant = task.generate(difficulty, rng)
        if not isinstance(variant, dict):
            raise PluginError('generate должна вернуть словарь с данными варианта')
        if task.validate is None or _accepts(task.validate, variant):
            break
    else:
        raise PluginError(
            f'за {GENERATION_TRIES} попыток generate не дала варианта, который принимает validate'
        )
    private_state: State = {'variant': variant}
    if task.interactive:
        private_state.update(initial=variant, moves=[])
    return _scene(task, variant), private_state


def _accepts(validate: Callable[[State], bool], variant: State) -> bool:
    verdict = validate(deepcopy(variant))
    if not isinstance(verdict, bool):
        raise PluginError('validate должна вернуть True или False')
    return verdict


def _evaluate(task: TaskType, answer: str, private_state: State) -> State:
    try:
        verdict = task.check(answer, deepcopy(private_state['variant']))
    except NotYet as wait:
        feedback = str(wait) or 'Ответ пока не завершает задачу.'
        return {'correct': False, 'should_finalize': False, 'feedback': feedback}
    if isinstance(verdict, bool):
        return {'correct': verdict}
    if isinstance(verdict, dict) and 'correct' in verdict:
        return verdict
    raise PluginError('check должна вернуть True или False')


def _reference(task: TaskType, private_state: State) -> tuple[str, list[str]]:
    solution = task.solution(deepcopy(private_state['variant']))
    answer, commands = solution if isinstance(solution, tuple) else (solution, [])
    return str(answer), [str(command) for command in commands]


def _whole(value: float) -> float:
    return int(value) if float(value).is_integer() else round(value, 6)


def _drop(text: str) -> tuple[str, float, float]:
    """Read ``drag:<name>:<x>:<y>``."""

    try:
        name, *numbers = text[len(DROP) :].split(':')
        x, y = (float(number) for number in numbers)
    except ValueError:
        x = y = math.nan
    if not (math.isfinite(x) and math.isfinite(y)):
        raise Rejected('Перенос записывается так: /op drag:<имя>:<x>:<y>.')
    return name, _whole(x), _whole(y)


def _landing(public_state: State, text: str) -> str:
    """The drop as the task type will receive it: on the step of the drawing and inside its ranges."""

    name, x, y = _drop(text)
    for block in public_state.get('blocks') or []:
        if block.get('type') != 'picture' or all(shape.get('drag') != name for shape in block['shapes']):
            continue
        step = block.get('snap')
        if step:
            x, y = round(x / step) * step, round(y / step) * step
        (left, right), (bottom, top) = block['x'], block['y']
        if not (left <= x <= right and bottom <= y <= top):
            raise Rejected('Объект нельзя вынести за пределы рисунка.')
        return f'{DROP}{name}:{_whole(x)}:{_whole(y)}'
    raise Rejected(f'На рисунке нет объекта {name}, который можно переносить.')


def _moved(task: TaskType, variant: State, text: str) -> tuple[State, str]:
    if task.drag is not None and text.startswith(DROP):
        handler, outcome = 'drag', task.drag(deepcopy(variant), *_drop(text))
    elif task.move is not None:
        handler, outcome = 'move', task.move(deepcopy(variant), text)
    else:
        raise Rejected('В этой задаче объекты только переносятся.')
    changed, message = outcome if isinstance(outcome, tuple) else (outcome, '')
    if not isinstance(changed, dict):
        raise PluginError(f'{handler} должна вернуть изменённый вариант или пару (вариант, сообщение)')
    return changed, str(message)


def _refusal(
    public_state: State, private_state: State, reason: str, message: str, text: str = ''
) -> Transition:
    return Transition(public_state, private_state, False, reason, message, text)


def _apply(task: TaskType, payload: State, public_state: State, private_state: State) -> Transition:
    text = required_text(payload, 'op_id', 'Нужно указать ход.')
    try:
        if task.drag is not None and text.startswith(DROP):
            text = _landing(public_state, text)
        variant, message = _moved(task, private_state['variant'], text)
    except Rejected as refusal:
        return _refusal(public_state, private_state, 'rejected', str(refusal) or 'Ход отклонён.', text)
    state = {**private_state, 'variant': variant, 'moves': [*private_state['moves'], text]}
    return Transition(_scene(task, variant), state, True, 'accepted', message or 'Ход принят.', text)


def _undo(task: TaskType, payload: State, public_state: State, private_state: State) -> Transition:
    if not private_state['moves']:
        return _refusal(public_state, private_state, 'nothing_to_undo', 'Отменять нечего.')
    moves = private_state['moves'][:-1]
    variant = private_state['initial']
    for text in moves:
        variant, _message = _moved(task, variant, text)
    state = {**private_state, 'variant': variant, 'moves': moves}
    return Transition(_scene(task, variant), state, True, 'accepted', 'Последний ход отменён.')


def _reset(task: TaskType, payload: State, public_state: State, private_state: State) -> Transition:
    state = {**private_state, 'variant': private_state['initial'], 'moves': []}
    return Transition(
        _scene(task, state['variant']), state, True, 'accepted', 'Задача возвращена в начальное состояние.'
    )


def _family(plugin: Plugin, task: TaskType) -> TaskFamily:
    moves = {'apply_op': _apply, 'undo': _undo, 'reset': _reset} if task.interactive else {}
    return TaskFamily(
        key=task.key,
        version=f'{plugin.name}-{plugin.version}',
        generate=partial(_generate, task),
        evaluate=partial(_evaluate, task),
        actions={name: partial(handler, task) for name, handler in moves.items()},
        reference_answer=partial(_reference, task) if task.solution is not None else None,
        ai_context=task.model_context,
        card=FamilyCard(
            title=task.title, description=task.description or plugin.description, author=plugin.author
        ),
    )
