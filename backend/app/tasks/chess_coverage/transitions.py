"""Participant actions on the board: place a piece, remove one, reset."""

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from sirius_gate.family import State, Transition

from .board import interaction_counts, piece_map, placement_state

Outcome = tuple[bool, str, str]

_PLACE_ACTION = re.compile(r'^place:([NBRQ]):([0-7]):([0-7])$', re.IGNORECASE)
_REMOVE_ACTION = re.compile(r'^remove:(P\d+)$', re.IGNORECASE)


def _normalized_action(
    action_type: str, op_id: str | None, client_action_id: str
) -> tuple[str, str, str, str]:
    """Action type, operation text, replay signature and action id of a well-formed request."""

    normalized_type = action_type.strip().casefold()
    if normalized_type not in {'apply_op', 'reset'}:
        raise ValueError('Chess placement action must be apply_op or reset')
    normalized_op = (op_id or '').strip()
    if normalized_type == 'apply_op' and not normalized_op:
        raise ValueError('apply_op requires op_id')
    normalized_input = normalized_op.casefold() if normalized_type == 'apply_op' else 'reset'
    action_id = client_action_id.strip()
    if not action_id:
        raise ValueError('client_action_id must not be empty')
    return normalized_type, normalized_op, normalized_input, action_id


def _replayed(
    previous: dict[str, Any], normalized_input: str, public_state: State, private_state: State
) -> Transition:
    if previous['normalized_input'] != normalized_input:
        raise ValueError('client_action_id was reused with another action')
    state = placement_state(private_state['placements'], private_state)
    return Transition(
        public_state=public_state,
        private_state=private_state,
        accepted=bool(previous['accepted']),
        completed=False,
        reason=str(previous['reason']),
        message=str(previous['message']),
        normalized_input=normalized_input,
        evaluation_state={**state, **interaction_counts(private_state['interaction'])},
    )


def _reset(private_state: State) -> Outcome:
    if not private_state['placements']:
        return False, 'already_at_start', 'На доске пока нет фигур.'
    interaction = private_state['interaction']
    private_state['placements'] = []
    interaction['reset_count'] = int(interaction['reset_count']) + 1
    return True, 'reset', 'Расстановка возвращена в начало.'


def _remove(private_state: State, placement_id: str) -> Outcome:
    placements = private_state['placements']
    remaining = [item for item in placements if item['id'] != placement_id]
    if len(remaining) == len(placements):
        return False, 'unknown_placement', 'Такой фигуры на доске нет.'
    interaction = private_state['interaction']
    private_state['placements'] = remaining
    interaction['removal_count'] = int(interaction['removal_count']) + 1
    return True, 'removed', f'Фигура {placement_id} убрана.'


def _placement_refusal(private_state: State, piece_id: str, row: int, col: int) -> tuple[str, str] | None:
    placements = private_state['placements']
    definitions = piece_map(private_state['piece_types'])
    targets = {tuple(point) for point in private_state['targets']}
    counts = {key: sum(1 for item in placements if item['piece'] == key) for key in definitions}
    if piece_id not in definitions:
        return 'unknown_piece', 'Такого типа фигуры нет.'
    if (row, col) in targets:
        return 'target_cell', 'На целевую клетку ставить фигуру нельзя.'
    if any(int(item['row']) == row and int(item['col']) == col for item in placements):
        return 'occupied_cell', 'Клетка уже занята другой фигурой.'
    if len(placements) >= int(private_state['max_placements']):
        return 'piece_budget', 'Лимит фигур исчерпан.'
    if counts[piece_id] >= int(definitions[piece_id]['limit']):
        return 'piece_limit', 'Лимит фигур этого типа исчерпан.'
    return None


def _place(private_state: State, piece_id: str, row: int, col: int) -> Outcome:
    refusal = _placement_refusal(private_state, piece_id, row, col)
    if refusal is not None:
        return False, *refusal
    interaction = private_state['interaction']
    placement_id = f'P{int(private_state["next_placement_number"])}'
    private_state['next_placement_number'] = int(private_state['next_placement_number']) + 1
    private_state['placements'].append({'id': placement_id, 'piece': piece_id, 'row': row, 'col': col})
    interaction['placement_count'] = int(interaction['placement_count']) + 1
    return True, 'placed', f'Фигура {placement_id} установлена.'


def _apply(private_state: State, op: str) -> Outcome:
    place_match = _PLACE_ACTION.fullmatch(op)
    remove_match = _REMOVE_ACTION.fullmatch(op)
    if remove_match:
        return _remove(private_state, remove_match.group(1).upper())
    if place_match:
        piece_id = place_match.group(1).upper()
        return _place(private_state, piece_id, int(place_match.group(2)), int(place_match.group(3)))
    return False, 'invalid_action', 'Не удалось распознать действие с фигурой.'


def transition_chess_coverage_action(
    *,
    action_type: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    client_action_id: str,
    op_id: str | None = None,
    first_action_latency_ms: int | None = None,
) -> Transition:
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

    if kind == 'reset':
        accepted, reason, message = _reset(next_private)
    else:
        accepted, reason, message = _apply(next_private, normalized_op)
    state = placement_state(next_private['placements'], next_private)
    shown = ('placements', 'piece_counts', 'covered_targets', 'total_cost', 'all_covered')
    next_public.update({key: state[key] for key in shown})
    message += (
        f' Покрыто {state["covered_count"]} из {state["target_count"]}; стоимость {state["total_cost"]}.'
    )
    processed[action_id] = {
        'normalized_input': normalized_input,
        'accepted': accepted,
        'reason': reason,
        'message': message,
    }
    return Transition(
        public_state=next_public,
        private_state=next_private,
        accepted=accepted,
        completed=False,
        reason=reason,
        message=message,
        normalized_input=normalized_input,
        evaluation_state={**state, **interaction_counts(interaction)},
    )
