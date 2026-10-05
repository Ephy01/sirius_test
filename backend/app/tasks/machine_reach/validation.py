"""Exact solver and self-checks of generated instances."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from copy import deepcopy

from sirius_gate.family import State

from .common import LEAPER_BOARD, state_key, witness_to
from .lamps import orthogonal_vector_separates
from .leaper import colours_differ, target_disconnected
from .numeric import residues_differ
from .operations import apply_operation, find_operation
from .permutations import parities_differ

CERTIFICATE_CHECKS: dict[str, Callable[[State, State, State, State], bool]] = {
    'gf2_orthogonal_vector': orthogonal_vector_separates,
    'residue_mod': residues_differ,
    'permutation_parity': parities_differ,
    'checkerboard_parity': colours_differ,
}


def simulate_witness(*, public_state: State, private_state: State) -> State | None:
    witness = private_state.get('witness')
    if not isinstance(witness, list):
        return None
    state = deepcopy(private_state['start'])
    for op_id in witness:
        operation = find_operation(public_state, str(op_id))
        if operation is None:
            return None
        result = apply_operation(
            sub_kind=str(private_state['sub_kind']),
            state=state,
            operation=operation,
            public_state=public_state,
        )
        if result is None:
            return None
        state = result
    return state


def shortest_witness(
    *, public_state: State, start: State | None = None, target: State | None = None
) -> list[str] | None:
    """Return an exact shortest operation sequence in the finite state graph."""

    initial = deepcopy(start if start is not None else public_state['start'])
    goal = target if target is not None else public_state['target']
    if initial == goal:
        return []
    sub_kind = str(public_state['sub_kind'])
    queue: deque[State] = deque([initial])
    start_key = state_key(initial)
    parents: dict[str, tuple[str, str] | None] = {start_key: None}
    while queue:
        current = queue.popleft()
        current_key = state_key(current)
        for operation in public_state['ops']:
            result = apply_operation(
                sub_kind=sub_kind, state=current, operation=operation, public_state=public_state
            )
            if result is None:
                continue
            result_key = state_key(result)
            if result_key in parents:
                continue
            parents[result_key] = (current_key, str(operation['id']))
            if result == goal:
                return witness_to(result_key, parents)
            queue.append(result)
    return None


def validate_unreachable_certificate(*, public_state: State, private_state: State) -> bool:
    certificate = private_state.get('certificate')
    if private_state.get('reachable') is not False or not isinstance(certificate, dict):
        return False
    kind = certificate.get('kind')
    start = private_state['start']
    target = private_state['target']
    check = CERTIFICATE_CHECKS.get(kind) if isinstance(kind, str) else None
    if check is not None:
        return check(certificate, start, target, public_state)
    if kind == 'disconnected_component' and private_state['sub_kind'] == LEAPER_BOARD:
        return target_disconnected(start, target, public_state)
    return False


def validate_machine_instance(*, public_state: State, private_state: State) -> bool:
    """Validate public/private consistency and the solver proof."""

    if public_state.get('sub_kind') != private_state.get('sub_kind'):
        return False
    if public_state.get('start') != private_state.get('start'):
        return False
    if public_state.get('target') != private_state.get('target'):
        return False
    if private_state.get('start') == private_state.get('target'):
        return False
    if private_state.get('reachable'):
        witness = private_state.get('witness')
        exact_witness = shortest_witness(public_state=public_state)
        return (
            isinstance(witness, list)
            and len(witness) == private_state.get('min_len')
            and len(witness) >= 2
            and exact_witness is not None
            and len(exact_witness) == len(witness)
            and simulate_witness(public_state=public_state, private_state=private_state)
            == private_state.get('target')
            and private_state.get('certificate') is None
        )
    return (
        private_state.get('witness') is None
        and private_state.get('min_len') is None
        and validate_unreachable_certificate(public_state=public_state, private_state=private_state)
    )
