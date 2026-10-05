"""perm_puzzle: reorder cards with two fixed even permutations."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable

from sirius_gate.family import State

from .common import (
    DISTANCE_RANGES,
    MACHINE_PANEL_KIND,
    PERM_PUZZLE,
    Operation,
    checked_difficulty,
    is_reachable_seed,
    machine_task,
    operation,
    seeded_rng,
    witness_to,
)

Permutation = tuple[int, ...]

PROMPT = 'Переставьте карточки в целевой порядок с помощью двух показанных операций или укажите, что это невозможно.'


def _cycle_permutation(n: int, cycle: Permutation) -> Permutation:
    permutation = list(range(n))
    for source, destination in zip(cycle, (*cycle[1:], cycle[0]), strict=True):
        permutation[destination] = source
    return tuple(permutation)


def _permutation_parity(values: Iterable[int]) -> int:
    items = list(values)
    inversions = sum(
        items[left] > items[right] for left in range(len(items)) for right in range(left + 1, len(items))
    )
    return inversions % 2


def _apply_permutation(values: Permutation, mapping: Permutation) -> Permutation:
    return tuple(values[mapping[index]] for index in range(len(values)))


def _bfs_permutations(
    *, start: Permutation, ops: list[Operation]
) -> tuple[dict[Permutation, int], dict[Permutation, tuple[Permutation, str] | None]]:
    mappings = {str(op['id']): tuple(int(item) for item in op['spec']['mapping']) for op in ops}
    distances = {start: 0}
    parents: dict[Permutation, tuple[Permutation, str] | None] = {start: None}
    queue: deque[Permutation] = deque([start])
    while queue:
        current = queue.popleft()
        for op_id, mapping in mappings.items():
            result = _apply_permutation(current, mapping)
            if result in distances:
                continue
            distances[result] = distances[current] + 1
            parents[result] = (current, op_id)
            queue.append(result)
    return distances, parents


def _all_permutations(n: int) -> list[Permutation]:
    result: list[Permutation] = [()]
    for value in range(n):
        result = [
            (*prefix[:index], value, *prefix[index:]) for prefix in result for index in range(len(prefix) + 1)
        ]
    return result


def _even_cycles(rng: random.Random, n: int) -> tuple[Permutation, Permutation]:
    """A 3-cycle and a 5-cycle over randomly relabelled positions."""

    labels = list(range(n))
    rng.shuffle(labels)
    relabel = tuple(labels)
    first_cycle = tuple(relabel[index] for index in (0, 1, 2))
    second_indices = (1, 2, 3, 4, 5) if n == 6 else (0, 1, 2, 3, 4)
    second_cycle = tuple(relabel[index] for index in second_indices)
    mappings = (_cycle_permutation(n, first_cycle), _cycle_permutation(n, second_cycle))
    if any(_permutation_parity(mapping) != 0 for mapping in mappings):
        raise RuntimeError('Permutation machine operations must remain even')
    return mappings


def _reorder_ops(mappings: tuple[Permutation, ...]) -> list[Operation]:
    return [
        operation(index, f'Перестановка {chr(1040 + index)}', {'kind': 'reorder', 'mapping': list(mapping)})
        for index, mapping in enumerate(mappings)
    ]


def _reachable_target(
    rng: random.Random, start: Permutation, ops: list[Operation], difficulty: int
) -> tuple[Permutation, list[str]]:
    distances, parents = _bfs_permutations(start=start, ops=ops)
    minimum, maximum = DISTANCE_RANGES[difficulty]
    candidates = sorted(state for state, distance in distances.items() if minimum <= distance <= maximum)
    if not candidates:
        farthest = max(distances.values())
        candidates = sorted(state for state, distance in distances.items() if distance == farthest)
    target = rng.choice(candidates)
    return target, witness_to(target, parents)


def _unreachable_target(rng: random.Random, start: Permutation, n: int) -> tuple[Permutation, State]:
    opposite_parity = 1 - _permutation_parity(start)
    candidates = [
        permutation
        for permutation in _all_permutations(n)
        if _permutation_parity(permutation) == opposite_parity
    ]
    target = rng.choice(candidates)
    certificate = {
        'kind': 'permutation_parity',
        'start_parity': _permutation_parity(start),
        'target_parity': _permutation_parity(target),
    }
    return target, certificate


def generate_perm_puzzle_task(*, seed: int, difficulty: int) -> tuple[State, State]:
    difficulty = checked_difficulty(difficulty)
    rng = seeded_rng(seed, PERM_PUZZLE)
    reachable = is_reachable_seed(seed, PERM_PUZZLE)
    n = 5 if difficulty == 1 else 6

    ops = _reorder_ops(_even_cycles(rng, n))
    start = tuple(rng.sample(range(n), n))
    witness, certificate = None, None
    if reachable:
        target, witness = _reachable_target(rng, start, ops, difficulty)
    else:
        target, certificate = _unreachable_target(rng, start, n)
    return machine_task(
        kind=MACHINE_PANEL_KIND,
        sub_kind=PERM_PUZZLE,
        prompt=PROMPT,
        difficulty=difficulty,
        ops=ops,
        start={'cards': [value + 1 for value in start]},
        target={'cards': [value + 1 for value in target]},
        witness=witness,
        certificate=certificate,
        extra_public={'card_count': n},
    )


def apply_reorder(state: State, spec: State, public_state: State) -> State:
    zero_based = tuple(int(value) - 1 for value in state['cards'])
    mapping = tuple(int(value) for value in spec['mapping'])
    result = _apply_permutation(zero_based, mapping)
    return {'cards': [value + 1 for value in result]}


def parities_differ(certificate: State, start: State, target: State, public_state: State) -> bool:
    start_values = [int(value) for value in start['cards']]
    target_values = [int(value) for value in target['cards']]
    return all(
        _permutation_parity(op['spec']['mapping']) == 0 for op in public_state['ops']
    ) and _permutation_parity(start_values) != _permutation_parity(target_values)
