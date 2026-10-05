"""numeric_machine: reach an integer with affine operations inside a working range."""

from __future__ import annotations

import random
from collections import deque

from sirius_gate.family import State

from .common import (
    DISTANCE_RANGES,
    MACHINE_PANEL_KIND,
    NUMERIC_MACHINE,
    Operation,
    checked_difficulty,
    is_reachable_seed,
    machine_task,
    operation,
    seeded_rng,
    witness_to,
)

PROMPT = (
    'Получите целое число на целевом экране с помощью показанных операций или укажите, что цель недостижима.'
)


def _numeric_next(value: int, spec: State, lower: int, upper: int) -> int | None:
    result = int(spec['a']) * value + int(spec['b'])
    return result if lower <= result <= upper else None


def _bfs_numeric(
    *, start: int, ops: list[Operation], lower: int, upper: int
) -> tuple[dict[int, int], dict[int, tuple[int, str] | None]]:
    distances = {start: 0}
    parents: dict[int, tuple[int, str] | None] = {start: None}
    queue: deque[int] = deque([start])
    while queue:
        current = queue.popleft()
        for op in ops:
            result = _numeric_next(current, op['spec'], lower, upper)
            if result is None or result in distances:
                continue
            distances[result] = distances[current] + 1
            parents[result] = (current, str(op['id']))
            queue.append(result)
    return distances, parents


def _shift_ops(increments: list[int]) -> list[Operation]:
    return [
        operation(
            index,
            f'x ↦ x − {abs(increment)}' if increment < 0 else f'x ↦ x + {increment}',
            {'kind': 'affine', 'a': 1, 'b': increment},
        )
        for index, increment in enumerate(increments)
    ]


def _reachable_target(
    rng: random.Random, start_value: int, ops: list[Operation], span: int, difficulty: int
) -> tuple[int, list[str]]:
    distances, parents = _bfs_numeric(start=start_value, ops=ops, lower=-span, upper=span)
    minimum, maximum = DISTANCE_RANGES[difficulty]
    candidates = sorted(value for value, distance in distances.items() if minimum <= distance <= maximum)
    if not candidates:
        raise RuntimeError('Numeric machine has no target in the requested range')
    target_value = rng.choice(candidates)
    return target_value, witness_to(target_value, parents)


def _unreachable_target(rng: random.Random, start_value: int, modulus: int, span: int) -> tuple[int, State]:
    candidates = [value for value in range(-span, span + 1) if value % modulus != start_value % modulus]
    target_value = rng.choice(candidates)
    certificate = {
        'kind': 'residue_mod',
        'modulus': modulus,
        'start_residue': start_value % modulus,
        'target_residue': target_value % modulus,
    }
    return target_value, certificate


def generate_numeric_machine_task(*, seed: int, difficulty: int) -> tuple[State, State]:
    difficulty = checked_difficulty(difficulty)
    rng = seeded_rng(seed, NUMERIC_MACHINE)
    reachable = is_reachable_seed(seed, NUMERIC_MACHINE)
    modulus = rng.randint(3 + difficulty, 6 + 2 * difficulty)
    span = modulus * (18 + difficulty * 3)

    increments = [modulus, -modulus]
    if difficulty >= 3:
        increments.append(rng.choice((-2, 2)) * modulus)
    ops = _shift_ops(increments)
    start_value = rng.randint(-2, 2) * modulus + rng.randrange(modulus)
    witness, certificate = None, None
    if reachable:
        target_value, witness = _reachable_target(rng, start_value, ops, span, difficulty)
    else:
        target_value, certificate = _unreachable_target(rng, start_value, modulus, span)
    return machine_task(
        kind=MACHINE_PANEL_KIND,
        sub_kind=NUMERIC_MACHINE,
        prompt=PROMPT,
        difficulty=difficulty,
        ops=ops,
        start={'value': start_value},
        target={'value': target_value},
        witness=witness,
        certificate=certificate,
        extra_public={'working_range': {'min': -span, 'max': span}},
    )


def apply_affine(state: State, spec: State, public_state: State) -> State | None:
    bounds = public_state['working_range']
    result = _numeric_next(int(state['value']), spec, int(bounds['min']), int(bounds['max']))
    return None if result is None else {'value': result}


def residues_differ(certificate: State, start: State, target: State, public_state: State) -> bool:
    modulus = int(certificate['modulus'])
    return (
        modulus > 1
        and all(
            int(op['spec']['a']) % modulus == 1 % modulus and int(op['spec']['b']) % modulus == 0
            for op in public_state['ops']
        )
        and int(start['value']) % modulus != int(target['value']) % modulus
    )
