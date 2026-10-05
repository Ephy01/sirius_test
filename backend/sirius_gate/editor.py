"""Entry point of the task editor, which runs this package in the author's browser.

The editor sends a request as JSON text and receives JSON text back. Replies have
the shapes of the HTTP API, so the client reads both sources the same way.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict

from . import sandbox
from .catalog import describe
from .check import check_family, render
from .family import State, TaskFamily
from .loading import load_source

MODULE = 'task'
CHECK_SEEDS = 40

# Families of the last text that loaded: a text with an error leaves the open task playable.
_families: dict[str, TaskFamily] = {}


class FamilyUnknown(sandbox.SandboxError):
    code = 'TASK_FAMILY_UNKNOWN'


def _family(key: str) -> TaskFamily:
    if key not in _families:
        raise FamilyUnknown('Такого семейства в коде задачи нет. Запустите код ещё раз.')
    return _families[key]


def _load(source: str) -> State:
    module = load_source(source, MODULE)
    if module.error is not None:
        raise sandbox.TaskCodeFailed(module.error)
    _families.clear()
    _families.update({family.key: family for family in module.families})
    return _catalog()


def _catalog() -> State:
    return {'items': [describe(family, MODULE) for family in _families.values()], 'problems': []}


def _generate(
    family: str, difficulty: int = 1, seed: int | None = None, sub_kind: str | None = None
) -> State:
    return sandbox.generate(_family(family), difficulty=difficulty, seed=seed, sub_kind=sub_kind)


def _interact(
    family: str, action_type: str, state: str, probe: str | None = None, op_id: str | None = None
) -> State:
    return sandbox.interact(_family(family), action_type=action_type, state=state, probe=probe, op_id=op_id)


def _answer(family: str, answer: str, state: str) -> State:
    return sandbox.answer(_family(family), answer=answer, state=state)


def _check(family: str, seeds: int = CHECK_SEEDS) -> State:
    record = _family(family)
    levels = check_family(record, seeds)
    return {
        'family': record.key,
        'seeds': seeds,
        'levels': [asdict(level) for level in levels],
        'report': render(record, levels, seeds),
    }


OPERATIONS: dict[str, Callable[..., State]] = {
    'load': _load,
    'catalog': _catalog,
    'generate': _generate,
    'interact': _interact,
    'answer': _answer,
    'check': _check,
}


def handle(request: str) -> str:
    """Run one request ``{"op": ..., "args": {...}}`` and reply ``{"result": ...}`` or ``{"error": ...}``."""

    call = json.loads(request)
    try:
        reply = json.dumps({'result': OPERATIONS[call['op']](**call.get('args', {}))}, allow_nan=False)
    except sandbox.SandboxError as error:
        reply = json.dumps({'error': {'code': error.code, 'message': str(error)}})
    except (TypeError, ValueError) as error:
        message = f'Ответ кода задачи нельзя записать в JSON: {error}'
        reply = json.dumps({'error': {'code': sandbox.TaskCodeFailed.code, 'message': message}})
    return reply
