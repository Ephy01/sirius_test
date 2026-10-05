"""Participant actions on a machine: apply an operation, undo, reset."""

from __future__ import annotations

from copy import deepcopy

from sirius_gate.family import State, Transition

from .common import LEAPER_BOARD, state_key
from .leaper import current_board
from .operations import apply_operation, find_operation

Outcome = tuple[bool, str, str]


def _normalized_action(
    action_type: str, op_id: str | None, client_action_id: str
) -> tuple[str, str, str, str]:
    """Action type, operation id, replay signature and action id of a well-formed request."""

    normalized_type = action_type.strip().casefold()
    if normalized_type not in {'apply_op', 'undo', 'reset'}:
        raise ValueError('Machine action_type must be apply_op, undo, or reset')
    normalized_op = (op_id or '').strip()
    if normalized_type == 'apply_op' and not normalized_op:
        raise ValueError('apply_op requires op_id')
    normalized_input = f'apply_op:{normalized_op}' if normalized_type == 'apply_op' else normalized_type
    action_id = client_action_id.strip()
    if not action_id:
        raise ValueError('client_action_id must not be empty')
    return normalized_type, normalized_op, normalized_input, action_id


def _replayed(
    previous: State, normalized_input: str, public_state: State, private_state: State
) -> Transition:
    if previous['normalized_input'] != normalized_input:
        raise ValueError('client_action_id was reused with another action')
    return Transition(
        public_state=public_state,
        private_state=private_state,
        accepted=bool(previous['accepted']),
        completed=False,
        reason=str(previous['reason']),
        message=str(previous['message']),
        normalized_input=normalized_input,
    )


def _apply(public_state: State, private_state: State, op_id: str) -> Outcome:
    operation = find_operation(public_state, op_id)
    if operation is None:
        return False, 'unknown_operation', 'Операция не распознана. Состояние не изменилось.'
    result = apply_operation(
        sub_kind=str(private_state['sub_kind']),
        state=private_state['current'],
        operation=operation,
        public_state=public_state,
    )
    if result is None:
        return False, 'operation_unavailable', 'Операция сейчас неприменима. Состояние не изменилось.'
    if result == private_state['current']:
        return False, 'no_effect', 'Операция не меняет состояние.'
    interaction = private_state['interaction']
    private_state['history'].append(deepcopy(private_state['current']))
    private_state['current'] = result
    interaction['apply_count'] = int(interaction['apply_count']) + 1
    result_key = state_key(result)
    if result_key in interaction['visited_state_keys']:
        interaction['revisited_count'] = int(interaction['revisited_count']) + 1
    else:
        interaction['visited_state_keys'].append(result_key)
    return True, 'applied', 'Операция применена.'


def _undo(private_state: State) -> Outcome:
    if not private_state['history']:
        return False, 'nothing_to_undo', 'Отменять нечего. Состояние не изменилось.'
    interaction = private_state['interaction']
    private_state['current'] = private_state['history'].pop()
    interaction['undo_count'] = int(interaction['undo_count']) + 1
    return True, 'undone', 'Последняя операция отменена.'


def _reset(private_state: State) -> Outcome:
    if private_state['current'] == private_state['start']:
        return False, 'already_at_start', 'Машина уже находится в начальном состоянии.'
    interaction = private_state['interaction']
    private_state['current'] = deepcopy(private_state['start'])
    private_state['history'] = []
    interaction['reset_count'] = int(interaction['reset_count']) + 1
    return True, 'reset', 'Машина возвращена в начальное состояние.'


def _refresh_dynamic_public(public_state: State, private_state: State) -> None:
    public_state['current'] = deepcopy(private_state['current'])
    public_state['steps_taken'] = len(private_state['history'])
    if private_state['sub_kind'] == LEAPER_BOARD:
        public_state['board'] = current_board(public_state, private_state)


def transition_machine_action(
    *,
    action_type: str,
    public_state: State,
    private_state: State,
    client_action_id: str,
    op_id: str | None = None,
    first_action_latency_ms: int | None = None,
) -> Transition:
    """Apply or undo one operation without mutating the supplied states.

    The transition itself is idempotent.  Replaying a ``client_action_id`` with
    the same payload returns the already-materialized state unchanged; reusing
    it for another payload raises ``ValueError``.
    """

    kind, normalized_op, normalized_input, action_id = _normalized_action(
        action_type, op_id, client_action_id
    )
    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    interaction = next_private['interaction']
    processed = interaction['processed_actions']
    previous = processed.get(action_id)
    if previous is not None:
        return _replayed(previous, normalized_input, next_public, next_private)
    if interaction['first_action_latency_ms'] is None and first_action_latency_ms is not None:
        interaction['first_action_latency_ms'] = max(0, int(first_action_latency_ms))

    if kind == 'apply_op':
        accepted, reason, message = _apply(next_public, next_private, normalized_op)
    elif kind == 'undo':
        accepted, reason, message = _undo(next_private)
    else:
        accepted, reason, message = _reset(next_private)
    processed[action_id] = {
        'normalized_input': normalized_input,
        'accepted': accepted,
        'reason': reason,
        'message': message,
    }
    _refresh_dynamic_public(next_public, next_private)
    return Transition(
        public_state=next_public,
        private_state=next_private,
        accepted=accepted,
        completed=False,
        reason=reason,
        message=message,
        normalized_input=normalized_input,
    )
