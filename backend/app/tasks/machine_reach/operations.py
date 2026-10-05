"""How one operation changes the state of each sub-kind."""

from __future__ import annotations

from collections.abc import Callable

from sirius_gate.family import State

from .common import LAMPS_GF2, LEAPER_BOARD, NUMERIC_MACHINE, PERM_PUZZLE, Operation
from .lamps import apply_toggle
from .leaper import apply_leap
from .numeric import apply_affine
from .permutations import apply_reorder

APPLY: dict[str, Callable[[State, State, State], State | None]] = {
    LAMPS_GF2: apply_toggle,
    NUMERIC_MACHINE: apply_affine,
    PERM_PUZZLE: apply_reorder,
    LEAPER_BOARD: apply_leap,
}


def find_operation(public_state: State, op_id: str) -> Operation | None:
    return next(
        (op for op in public_state.get('ops', []) if isinstance(op, dict) and op.get('id') == op_id), None
    )


def apply_operation(
    *, sub_kind: str, state: State, operation: Operation, public_state: State
) -> State | None:
    """The state after ``operation``, or ``None`` when it cannot be applied in ``state``."""

    spec = operation['spec']
    apply = APPLY.get(sub_kind)
    if apply is None:
        raise ValueError(f'Unsupported machine sub-kind: {sub_kind!r}')
    return apply(state, spec, public_state)
