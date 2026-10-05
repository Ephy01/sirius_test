"""Playing a task outside a contest, the way the author sandbox does.

Nothing is stored between calls. Both states are returned as the text ``state``
and the caller passes it back untouched: a browser that parsed it into JavaScript
numbers would return integers above 2**53 changed.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from typing import Any

from .errors import explain
from .family import State, TaskFamily

# A browser reads the seed as a JavaScript number, which is exact only up to 2**53.
SEED_BITS = 53


class SandboxError(Exception):
    """A sandbox call that cannot be completed. ``code`` is what the API reports."""

    code = 'SANDBOX_FAILED'


class TaskCodeFailed(SandboxError):
    code = 'TASK_CODE_FAILED'


class StateInvalid(SandboxError):
    code = 'SANDBOX_STATE_INVALID'


class ActionNotSupported(SandboxError):
    code = 'TASK_INTERACTION_ACTION_NOT_SUPPORTED'


def _run(step: Callable[[], Any]) -> Any:
    """Call task code and turn its failure into a message the author can read."""

    try:
        return step()
    except Exception as error:
        raise TaskCodeFailed(explain(error)) from error


def _state_text(public_state: State, private_state: State) -> str:
    return json.dumps(
        {'private_state': private_state, 'public_state': public_state}, ensure_ascii=False, indent=2
    )


def _states(text: str) -> tuple[State, State]:
    try:
        state = json.loads(text)
        public_state, private_state = state['public_state'], state['private_state']
    except (ValueError, KeyError, TypeError):
        public_state = private_state = None
    if not isinstance(public_state, dict) or not isinstance(private_state, dict):
        raise StateInvalid('Состояние задачи повреждено. Сгенерируйте вариант заново.')
    return public_state, private_state


def _reference(family: TaskFamily, private_state: State) -> State:
    answer, commands = (
        _run(lambda: family.reference_answer(private_state)) if family.reference_answer else (None, [])
    )
    details = _run(lambda: family.debug_details(private_state)) if family.debug_details else []
    return {'reference_answer': answer, 'reference_commands': list(commands), 'details': list(details)}


def generate(
    family: TaskFamily, *, difficulty: int = 1, seed: int | None = None, sub_kind: str | None = None
) -> State:
    """A task of the family; without ``seed`` a random one is chosen and reported."""

    seed = secrets.randbits(SEED_BITS) if seed is None else seed
    context = {'sub_kinds': [sub_kind]} if sub_kind else {}
    public_state, private_state = _run(lambda: family.generate(seed, difficulty, context))
    return {
        'family': family.key,
        'generator_version': family.version,
        'seed': seed,
        'difficulty': difficulty,
        'public_state': public_state,
        'state': _state_text(public_state, private_state),
        **_reference(family, private_state),
    }


def interact(
    family: TaskFamily, *, action_type: str, state: str, probe: str | None = None, op_id: str | None = None
) -> State:
    """Apply one action of the participant to the task kept in ``state``."""

    action = family.actions.get(action_type)
    if action is None:
        raise ActionNotSupported('Эта команда не поддерживается текущей задачей.')
    public_state, private_state = _states(state)
    arguments = {'probe': probe, 'op_id': op_id}
    payload = {
        **{key: value for key, value in arguments.items() if value is not None},
        'client_action_id': secrets.token_hex(8),
        'first_action_latency_ms': 0,
    }
    transition = _run(lambda: action(payload, public_state, private_state))
    return {
        'public_state': transition.public_state,
        'state': _state_text(transition.public_state, transition.private_state),
        'accepted': transition.accepted,
        'completed': transition.completed,
        'reason': transition.reason,
        'message': transition.message,
        'evaluation': transition.evaluation_state,
        **_reference(family, transition.private_state),
    }


def answer(family: TaskFamily, *, answer: str, state: str) -> State:
    """Check an answer against the task kept in ``state``."""

    _public_state, private_state = _states(state)
    evaluation = dict(_run(lambda: family.evaluate(answer, private_state)))
    return {'evaluation': evaluation, 'finalized': evaluation.get('should_finalize') is not False}
