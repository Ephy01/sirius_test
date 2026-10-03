"""leaper_board: bring a leaping piece to a marked cell of a board with obstacles."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from ..family import State
from .common import (
    CHESS_KIND,
    DISTANCE_RANGES,
    LEAPER_BOARD,
    MAX_GENERATION_ATTEMPTS,
    Operation,
    checked_difficulty,
    is_reachable_seed,
    machine_task,
    operation,
    seeded_rng,
    witness_to,
)

Point = tuple[int, int]
Route = tuple[Point, Point, list[str] | None]

JUMP_CATALOG = ((1, 1), (0, 2), (1, 3))
MIN_FREE_CELLS = 8
PROMPT = 'Переведите фигуру на отмеченную клетку разрешёнными прыжками. Клетки с препятствиями недоступны.'


@dataclass(frozen=True)
class _Layout:
    """A square board with obstacles; ``free`` keeps the order in which start cells are tried."""

    size: int
    jump: Point
    vectors: tuple[Point, ...]
    blocked: frozenset[Point]
    free: list[Point]

    @property
    def board(self) -> dict[str, Any]:
        return {'rows': self.size, 'cols': self.size, 'blocked': self.blocked, 'vectors': self.vectors}


def _leaper_vectors(a: int, b: int) -> tuple[Point, ...]:
    vectors = {
        (row_sign * row_delta, col_sign * col_delta)
        for row_delta, col_delta in {(a, b), (b, a)}
        for row_sign in (-1, 1)
        for col_sign in (-1, 1)
        if row_delta or col_delta
    }
    return tuple(sorted(vectors))


def _inside(row: int, col: int, rows: int, cols: int) -> bool:
    return 0 <= row < rows and 0 <= col < cols


def _leaper_neighbors(
    point: Point, *, rows: int, cols: int, blocked: frozenset[Point], vectors: tuple[Point, ...]
) -> tuple[Point, ...]:
    row, col = point
    return tuple(
        sorted(
            (row + row_delta, col + col_delta)
            for row_delta, col_delta in vectors
            if _inside(row + row_delta, col + col_delta, rows, cols)
            and (row + row_delta, col + col_delta) not in blocked
        )
    )


def bfs_leaper(
    *, start: Point, rows: int, cols: int, blocked: frozenset[Point], vectors: tuple[Point, ...]
) -> tuple[dict[Point, int], dict[Point, tuple[Point, str] | None]]:
    vector_ids = {vector: f'op{index + 1}' for index, vector in enumerate(vectors)}
    distances = {start: 0}
    parents: dict[Point, tuple[Point, str] | None] = {start: None}
    queue: deque[Point] = deque([start])
    while queue:
        current = queue.popleft()
        for destination in _leaper_neighbors(current, rows=rows, cols=cols, blocked=blocked, vectors=vectors):
            if destination in distances:
                continue
            delta = (destination[0] - current[0], destination[1] - current[1])
            distances[destination] = distances[current] + 1
            parents[destination] = (current, vector_ids[delta])
            queue.append(destination)
    return distances, parents


def _point_state(point: Point) -> State:
    return {'row': point[0], 'col': point[1]}


def _leap_label(row_delta: int, col_delta: int) -> str:
    """Словесная подпись прыжка: строка 1 — верхняя, поэтому −строка = вверх."""

    parts = []
    if row_delta:
        direction = 'вверх' if row_delta < 0 else 'вниз'
        parts.append(f'на {abs(row_delta)} {direction}')
    if col_delta:
        direction = 'влево' if col_delta < 0 else 'вправо'
        parts.append(f'на {abs(col_delta)} {direction}')
    return 'Прыжок ' + ' и '.join(parts) if parts else 'Прыжок на месте'


def _public_chess_board(
    *, rows: int, cols: int, blocked: Iterable[Point], current: Point, target: Point
) -> list[list[str | None]]:
    blocked_set = set(blocked)
    board: list[list[str | None]] = []
    for row in range(rows - 1, -1, -1):
        rendered_row: list[str | None] = []
        for col in range(cols):
            point = (row, col)
            if point == current:
                rendered_row.append('wN')
            elif point == target:
                rendered_row.append('bK')
            elif point in blocked_set:
                rendered_row.append('bP')
            else:
                rendered_row.append(None)
        board.append(rendered_row)
    return board


def _random_layout(
    rng: random.Random, difficulty: int, attempt: int, size: int, points: list[Point]
) -> _Layout | None:
    diagonal_only = difficulty >= 4 or attempt >= MAX_GENERATION_ATTEMPTS // 2
    jump = (1, 1) if diagonal_only else rng.choice(JUMP_CATALOG)
    obstacle_ratio = rng.uniform(0.12, 0.30)
    blocked = frozenset(point for point in points if rng.random() < obstacle_ratio)
    free = [point for point in points if point not in blocked]
    if len(free) < MIN_FREE_CELLS:
        return None
    rng.shuffle(free)
    return _Layout(size=size, jump=jump, vectors=_leaper_vectors(*jump), blocked=blocked, free=free)


def _reachable_target(
    rng: random.Random, layout: _Layout, start: Point, difficulty: int
) -> tuple[Point, list[str]] | None:
    distances, parents = bfs_leaper(start=start, **layout.board)
    minimum, maximum = DISTANCE_RANGES[difficulty]
    candidates = sorted(point for point, distance in distances.items() if minimum <= distance <= maximum)
    if not candidates:
        return None
    target = rng.choice(candidates)
    return target, witness_to(target, parents)


def _unreachable_target(rng: random.Random, layout: _Layout, start: Point) -> tuple[Point, None] | None:
    """A free cell of the other colour: every catalogued jump keeps the colour of the cell."""

    candidates = sorted(
        point for point in layout.free if (point[0] + point[1]) % 2 != (start[0] + start[1]) % 2
    )
    return (rng.choice(candidates), None) if candidates else None


def _find_route(rng: random.Random, layout: _Layout, reachable: bool, difficulty: int) -> Route | None:
    for start in layout.free:
        if not _leaper_neighbors(start, **layout.board):
            continue
        if reachable:
            found = _reachable_target(rng, layout, start, difficulty)
        else:
            found = _unreachable_target(rng, layout, start)
        if found is not None:
            return start, *found
    return None


def _layout_with_route(rng: random.Random, difficulty: int, reachable: bool) -> tuple[_Layout, Route]:
    size = 6 if difficulty == 1 else 7 if difficulty <= 3 else 8
    points = [(row, col) for row in range(size) for col in range(size)]
    for attempt in range(MAX_GENERATION_ATTEMPTS):
        layout = _random_layout(rng, difficulty, attempt, size, points)
        if layout is None:
            continue
        route = _find_route(rng, layout, reachable, difficulty)
        if route is not None:
            return layout, route
    raise RuntimeError('Unable to generate a non-degenerate leaper board')


def _leap_ops(vectors: tuple[Point, ...]) -> list[Operation]:
    return [
        operation(
            index,
            _leap_label(row_delta, col_delta),
            {'kind': 'leap', 'row_delta': row_delta, 'col_delta': col_delta},
        )
        for index, (row_delta, col_delta) in enumerate(vectors)
    ]


def _parity_certificate(start: Point, target: Point, jump: Point) -> State:
    return {
        'kind': 'checkerboard_parity',
        'start_parity': (start[0] + start[1]) % 2,
        'target_parity': (target[0] + target[1]) % 2,
        'jump_sum_parity': (jump[0] + jump[1]) % 2,
    }


def generate_leaper_board_task(*, seed: int, difficulty: int) -> tuple[State, State]:
    difficulty = checked_difficulty(difficulty)
    rng = seeded_rng(seed, LEAPER_BOARD)
    reachable = is_reachable_seed(seed, LEAPER_BOARD)
    layout, (start, target, witness) = _layout_with_route(rng, difficulty, reachable)
    return machine_task(
        kind=CHESS_KIND,
        sub_kind=LEAPER_BOARD,
        prompt=PROMPT,
        difficulty=difficulty,
        ops=_leap_ops(layout.vectors),
        start=_point_state(start),
        target=_point_state(target),
        witness=witness,
        certificate=None if reachable else _parity_certificate(start, target, layout.jump),
        extra_public={
            'rows': layout.size,
            'cols': layout.size,
            'blocked': [_point_state(point) for point in sorted(layout.blocked)],
            'jump': {'a': layout.jump[0], 'b': layout.jump[1]},
            'board': _public_chess_board(
                rows=layout.size, cols=layout.size, blocked=layout.blocked, current=start, target=target
            ),
        },
    )


def _point(state: State) -> Point:
    return int(state['row']), int(state['col'])


def _blocked_points(public_state: State) -> Iterable[Point]:
    return ((int(point['row']), int(point['col'])) for point in public_state['blocked'])


def apply_leap(state: State, spec: State, public_state: State) -> State | None:
    row = int(state['row']) + int(spec['row_delta'])
    col = int(state['col']) + int(spec['col_delta'])
    blocked = set(_blocked_points(public_state))
    if not _inside(row, col, int(public_state['rows']), int(public_state['cols'])):
        return None
    if (row, col) in blocked:
        return None
    return {'row': row, 'col': col}


def current_board(public_state: State, private_state: State) -> list[list[str | None]]:
    """The public board redrawn for the current position of the piece."""

    return _public_chess_board(
        rows=int(public_state['rows']),
        cols=int(public_state['cols']),
        blocked=_blocked_points(public_state),
        current=_point(private_state['current']),
        target=_point(private_state['target']),
    )


def colours_differ(certificate: State, start: State, target: State, public_state: State) -> bool:
    vectors_preserve_colour = all(
        (int(op['spec']['row_delta']) + int(op['spec']['col_delta'])) % 2 == 0 for op in public_state['ops']
    )
    return (
        vectors_preserve_colour
        and (int(start['row']) + int(start['col'])) % 2 != (int(target['row']) + int(target['col'])) % 2
    )


def target_disconnected(start: State, target: State, public_state: State) -> bool:
    blocked = frozenset(_blocked_points(public_state))
    vectors = tuple(
        (int(op['spec']['row_delta']), int(op['spec']['col_delta'])) for op in public_state['ops']
    )
    distances, _parents = bfs_leaper(
        start=_point(start),
        rows=int(public_state['rows']),
        cols=int(public_state['cols']),
        blocked=blocked,
        vectors=vectors,
    )
    return _point(target) not in distances
