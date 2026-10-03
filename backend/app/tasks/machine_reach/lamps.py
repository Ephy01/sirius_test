"""lamps_gf2: toggle lamps with buttons that act as vectors over GF(2)."""

from __future__ import annotations

import random
from collections.abc import Iterable

from ..family import State
from .common import (
    LAMPS_GF2,
    MACHINE_PANEL_KIND,
    Operation,
    checked_difficulty,
    is_reachable_seed,
    machine_task,
    operation,
    seeded_rng,
)

LAMPS_DISTANCE_RANGES: dict[int, tuple[int, int]] = {1: (2, 3), 2: (3, 4), 3: (3, 5), 4: (4, 5), 5: (5, 5)}
PROMPT = (
    'Переведите лампы из начального состояния в целевое, нажимая '
    'показанные кнопки, или докажите, что это невозможно.'
)


def _gf2_rank(vectors: Iterable[int], n: int) -> int:
    basis = [0] * n
    rank = 0
    for original in vectors:
        vector = original
        while vector:
            pivot = vector.bit_length() - 1
            if basis[pivot]:
                vector ^= basis[pivot]
            else:
                basis[pivot] = vector
                rank += 1
                break
    return rank


def _gf2_span(vectors: list[int]) -> dict[int, list[int]]:
    paths: dict[int, list[int]] = {0: []}
    for index, vector in enumerate(vectors):
        additions = {
            value ^ vector: [*path, index]
            for value, path in tuple(paths.items())
            if value ^ vector not in paths
        }
        paths.update(additions)
    return paths


def _bits(value: int, n: int) -> list[int]:
    return [(value >> index) & 1 for index in range(n)]


def _from_bits(bits: Iterable[int]) -> int:
    value = 0
    for index, bit in enumerate(bits):
        if int(bit):
            value |= 1 << index
    return value


def _gf2_certificate(vectors: list[int], delta: int, n: int) -> State:
    for witness in range(1, 1 << n):
        if all((witness & vector).bit_count() % 2 == 0 for vector in vectors):
            if (witness & delta).bit_count() % 2 == 1:
                return {
                    'kind': 'gf2_orthogonal_vector',
                    'vector': _bits(witness, n),
                    'start_dot': 0,
                    'target_dot': 1,
                }
    raise RuntimeError('A vector outside a GF(2) span must have a separator')


def _independent_vectors(rng: random.Random, n: int, count: int) -> list[int]:
    vectors: list[int] = []
    while len(vectors) < count:
        candidate = rng.randrange(1, 1 << n)
        if _gf2_rank([*vectors, candidate], n) > len(vectors):
            vectors.append(candidate)
    return vectors


def _witness_lengths(difficulty: int, button_count: int) -> list[int]:
    minimum, maximum = LAMPS_DISTANCE_RANGES[difficulty]
    return list(range(minimum, min(maximum, button_count) + 1)) or [button_count]


def _reachable_delta(rng: random.Random, vectors: list[int], lengths: list[int]) -> tuple[int, list[str]]:
    witness_length = rng.choice(lengths)
    chosen = sorted(rng.sample(range(len(vectors)), witness_length))
    delta = 0
    for index in chosen:
        delta ^= vectors[index]
    return delta, [f'op{index + 1}' for index in chosen]


def _unreachable_delta(rng: random.Random, vectors: list[int], n: int) -> tuple[int, State]:
    span = _gf2_span(vectors)
    delta = rng.choice([value for value in range(1, 1 << n) if value not in span])
    return delta, _gf2_certificate(vectors, delta, n)


def _toggle_ops(vectors: list[int], n: int) -> list[Operation]:
    return [
        operation(
            index,
            f'Кнопка {index + 1}',
            {'kind': 'toggle', 'indices': [lamp for lamp, bit in enumerate(_bits(vector, n)) if bit]},
        )
        for index, vector in enumerate(vectors)
    ]


def generate_lamps_gf2_task(*, seed: int, difficulty: int) -> tuple[State, State]:
    difficulty = checked_difficulty(difficulty)
    rng = seeded_rng(seed, LAMPS_GF2)
    reachable = is_reachable_seed(seed, LAMPS_GF2)
    n = min(7, 5 + (difficulty - 1) // 2)
    button_count = min(5, max(3, difficulty + 1))

    vectors = _independent_vectors(rng, n, button_count)
    start_value = rng.randrange(1 << n)
    witness, certificate = None, None
    if reachable:
        delta, witness = _reachable_delta(rng, vectors, _witness_lengths(difficulty, button_count))
    else:
        delta, certificate = _unreachable_delta(rng, vectors, n)
    return machine_task(
        kind=MACHINE_PANEL_KIND,
        sub_kind=LAMPS_GF2,
        prompt=PROMPT,
        difficulty=difficulty,
        ops=_toggle_ops(vectors, n),
        start={'lamps': _bits(start_value, n)},
        target={'lamps': _bits(start_value ^ delta, n)},
        witness=witness,
        certificate=certificate,
        extra_public={'lamp_count': n},
    )


def apply_toggle(state: State, spec: State, public_state: State) -> State:
    lamps = [int(value) for value in state['lamps']]
    for index in spec['indices']:
        lamps[int(index)] ^= 1
    return {'lamps': lamps}


def orthogonal_vector_separates(certificate: State, start: State, target: State, public_state: State) -> bool:
    vector = _from_bits(certificate['vector'])
    start_value = _from_bits(start['lamps'])
    target_value = _from_bits(target['lamps'])
    button_vectors = [sum(1 << int(index) for index in op['spec']['indices']) for op in public_state['ops']]
    return (
        all((vector & button).bit_count() % 2 == 0 for button in button_vectors)
        and (vector & start_value).bit_count() % 2 != (vector & target_value).bit_count() % 2
    )
