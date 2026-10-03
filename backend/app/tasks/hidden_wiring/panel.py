"""The panel of hidden_wiring: chords of two buttons as vectors over GF(2)."""

from __future__ import annotations

import itertools
from collections import deque
from typing import Any

FAMILY_KEY = 'hidden_wiring'
GENERATOR_VERSION = 'hidden-wiring-v1'
PUBLIC_KIND = 'hidden_wiring'

CHORD_BUDGET = 8
EXAM_CHORD_COUNT = 3
REACH_VARIANT = 'reach_target'
PREDICT_VARIANT = 'predict_chords'

HINT_SCORE_MULTIPLIER = 0.7


def chord_id(first: int, second: int) -> str:
    return f'b{first + 1}+b{second + 1}'


def lamp_list(value: int, lamp_count: int) -> list[int]:
    return [(value >> index) & 1 for index in range(lamp_count)]


def span_rank(vectors: list[int]) -> int:
    basis: list[int] = []
    for vector in vectors:
        reduced = vector
        for base in basis:
            reduced = min(reduced, reduced ^ base)
        if reduced:
            basis.append(reduced)
            basis.sort(reverse=True)
    return len(basis)


def in_span(vector: int, vectors: list[int]) -> bool:
    return span_rank([*vectors, vector]) == span_rank(vectors)


def chord_effects(columns: list[int]) -> dict[str, int]:
    return {
        chord_id(first, second): columns[first] ^ columns[second]
        for first, second in itertools.combinations(range(len(columns)), 2)
    }


def chord_indicator(chord_id: str, button_count: int) -> int:
    first_token, second_token = chord_id.split('+')
    first = int(first_token[1:]) - 1
    second = int(second_token[1:]) - 1
    return (1 << first) | (1 << second)


def reach_certificate(
    *, effects: dict[str, int], allowed_chords: list[str], start: int, target: int
) -> list[str] | None:
    """Shortest chord sequence from ``start`` to ``target`` (BFS)."""

    if start == target:
        return []
    parents: dict[int, tuple[int, str]] = {start: (start, '')}
    queue: deque[int] = deque([start])
    while queue:
        current = queue.popleft()
        for chord in allowed_chords:
            nxt = current ^ effects[chord]
            if nxt in parents:
                continue
            parents[nxt] = (current, chord)
            if nxt == target:
                sequence: list[str] = []
                cursor = nxt
                while cursor != start:
                    previous, used = parents[cursor]
                    sequence.append(used)
                    cursor = previous
                sequence.reverse()
                return sequence
            queue.append(nxt)
    return None


def entropy_bits(private: dict[str, Any]) -> int:
    """Exact hypothesis entropy: L·(B−1−rank) bits.

    Chords only ever reveal sums of column pairs, so the recoverable
    knowledge lives in the even-weight indicator space of dimension B−1;
    every independent chord removes L bits.
    """

    lamp_count = int(private['lamp_count'])
    button_count = int(private['button_count'])
    indicators = [chord_indicator(chord, button_count) for chord in private.get('observed_chords', [])]
    rank = span_rank(indicators)
    return lamp_count * (button_count - 1 - rank)
