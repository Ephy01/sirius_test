"""Deterministic generators for the ``machine_reach`` task family.

The module deliberately has no database or HTTP dependencies.  A generated
task is a pair of JSON-compatible dictionaries.  State changes are expressed
as pure transitions, while persistence and authorization stay in the API
layer.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Literal

FAMILY_KEY = "machine_reach"
GENERATOR_VERSION = "machine-reach-v1"
MACHINE_PANEL_KIND = "machine_panel"
CHESS_KIND = "chess"

LAMPS_GF2 = "lamps_gf2"
NUMERIC_MACHINE = "numeric_machine"
PERM_PUZZLE = "perm_puzzle"
LEAPER_BOARD = "leaper_board"
SUB_KINDS = (LAMPS_GF2, NUMERIC_MACHINE, PERM_PUZZLE, LEAPER_BOARD)

STEPS_SOFT_CAP = 24
MAX_GENERATION_ATTEMPTS = 128
FILES = "abcdefgh"

State = dict[str, Any]
Operation = dict[str, Any]
SubKind = Literal[
    "lamps_gf2",
    "numeric_machine",
    "perm_puzzle",
    "leaper_board",
]

# The literal B.3 range cannot be reached by an XOR machine with at most five
# involutive buttons: every shortest word uses every independent button at
# most once.  The lamps radical therefore saturates at five; the other
# generators use the full family range.
DISTANCE_RANGES: dict[int, tuple[int, int]] = {
    1: (2, 3),
    2: (3, 5),
    3: (4, 7),
    4: (6, 9),
    5: (8, 12),
}
LAMPS_DISTANCE_RANGES: dict[int, tuple[int, int]] = {
    1: (2, 3),
    2: (3, 4),
    3: (3, 5),
    4: (4, 5),
    5: (5, 5),
}


@dataclass(frozen=True)
class MachineTransition:
    """Result of one pure machine operation.

    ``completed`` is intentionally always false: reaching the target does not
    finalize a task.  The participant explicitly submits ``/answer done``.
    """

    public_state: dict[str, Any]
    private_state: dict[str, Any]
    accepted: bool
    completed: bool
    goal_reached: bool
    reason: str
    message: str
    normalized_input: str
    evaluation_state: dict[str, Any] | None = None


def _difficulty(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError("Machine difficulty must be an integer from 1 to 5")
    return value


def _rng(seed: int, namespace: str) -> random.Random:
    digest = hashlib.sha256(
        f"{GENERATOR_VERSION}:{namespace}:{seed}".encode("ascii")
    ).digest()
    return random.Random(int.from_bytes(digest[:16], "big"))


def _is_reachable_seed(seed: int, sub_kind: str) -> bool:
    # Consecutive seeds contain exactly 50% of each class.  The namespace
    # changes which parity means reachable without changing the ratio.
    offset = SUB_KINDS.index(sub_kind)
    return (seed + offset) % 2 == 0


def _state_key(state: State) -> str:
    return json.dumps(state, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _initial_private(
    *,
    sub_kind: str,
    difficulty: int,
    reachable: bool,
    start: State,
    target: State,
    witness: list[str] | None,
    certificate: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "sub_kind": sub_kind,
        "difficulty": difficulty,
        "reachable": reachable,
        "start": deepcopy(start),
        "target": deepcopy(target),
        "current": deepcopy(start),
        "witness": list(witness) if witness is not None else None,
        "min_len": len(witness) if witness is not None else None,
        "certificate": deepcopy(certificate),
        "history": [],
        "interaction": {
            "apply_count": 0,
            "undo_count": 0,
            "revisited_count": 0,
            "visited_state_keys": [_state_key(start)],
            "first_action_latency_ms": None,
            "processed_actions": {},
        },
    }


def _base_public(
    *,
    kind: str,
    sub_kind: str,
    prompt: str,
    ops: list[Operation],
    start: State,
    target: State,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "sub_kind": sub_kind,
        "prompt": prompt,
        "ops": deepcopy(ops),
        "start": deepcopy(start),
        "target": deepcopy(target),
        "current": deepcopy(start),
        "steps_soft_cap": STEPS_SOFT_CAP,
        "steps_taken": 0,
    }


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


def _gf2_certificate(vectors: list[int], delta: int, n: int) -> dict[str, Any]:
    for witness in range(1, 1 << n):
        if all((witness & vector).bit_count() % 2 == 0 for vector in vectors):
            if (witness & delta).bit_count() % 2 == 1:
                return {
                    "kind": "gf2_orthogonal_vector",
                    "vector": _bits(witness, n),
                    "start_dot": 0,
                    "target_dot": 1,
                }
    raise RuntimeError("A vector outside a GF(2) span must have a separator")


def generate_lamps_gf2_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = _difficulty(difficulty)
    rng = _rng(seed, LAMPS_GF2)
    reachable = _is_reachable_seed(seed, LAMPS_GF2)
    n = min(7, 5 + (difficulty - 1) // 2)
    button_count = min(5, max(3, difficulty + 1))

    vectors: list[int] = []
    while len(vectors) < button_count:
        candidate = rng.randrange(1, 1 << n)
        if _gf2_rank([*vectors, candidate], n) > len(vectors):
            vectors.append(candidate)

    span = _gf2_span(vectors)
    minimum, maximum = LAMPS_DISTANCE_RANGES[difficulty]
    allowed_lengths = [
        length for length in range(minimum, min(maximum, button_count) + 1)
    ]
    if not allowed_lengths:
        allowed_lengths = [button_count]

    start_value = rng.randrange(1 << n)
    witness: list[str] | None
    certificate: dict[str, Any] | None
    if reachable:
        witness_length = rng.choice(allowed_lengths)
        chosen = sorted(rng.sample(range(button_count), witness_length))
        delta = 0
        for index in chosen:
            delta ^= vectors[index]
        witness = [f"op{index + 1}" for index in chosen]
        certificate = None
    else:
        outside = [value for value in range(1, 1 << n) if value not in span]
        delta = rng.choice(outside)
        witness = None
        certificate = _gf2_certificate(vectors, delta, n)
    target_value = start_value ^ delta

    ops = [
        {
            "id": f"op{index + 1}",
            "label": f"Кнопка {index + 1}",
            "spec": {
                "kind": "toggle",
                "indices": [
                    lamp_index
                    for lamp_index, bit in enumerate(_bits(vector, n))
                    if bit
                ],
            },
        }
        for index, vector in enumerate(vectors)
    ]
    start = {"lamps": _bits(start_value, n)}
    target = {"lamps": _bits(target_value, n)}
    public = _base_public(
        kind=MACHINE_PANEL_KIND,
        sub_kind=LAMPS_GF2,
        prompt=(
            "Переведите лампы из начального состояния в целевое, нажимая "
            "показанные кнопки, или докажите, что это невозможно."
        ),
        ops=ops,
        start=start,
        target=target,
    )
    public["lamp_count"] = n
    private = _initial_private(
        sub_kind=LAMPS_GF2,
        difficulty=difficulty,
        reachable=reachable,
        start=start,
        target=target,
        witness=witness,
        certificate=certificate,
    )
    return public, private


def _numeric_next(
    value: int,
    spec: dict[str, Any],
    lower: int,
    upper: int,
) -> int | None:
    result = int(spec["a"]) * value + int(spec["b"])
    return result if lower <= result <= upper else None


def _bfs_numeric(
    *,
    start: int,
    ops: list[Operation],
    lower: int,
    upper: int,
) -> tuple[dict[int, int], dict[int, tuple[int, str] | None]]:
    distances = {start: 0}
    parents: dict[int, tuple[int, str] | None] = {start: None}
    queue: deque[int] = deque([start])
    while queue:
        current = queue.popleft()
        for op in ops:
            result = _numeric_next(current, op["spec"], lower, upper)
            if result is None or result in distances:
                continue
            distances[result] = distances[current] + 1
            parents[result] = (current, str(op["id"]))
            queue.append(result)
    return distances, parents


def _restore_scalar_witness(
    target: int,
    parents: dict[int, tuple[int, str] | None],
) -> list[str]:
    witness: list[str] = []
    cursor = target
    while parents[cursor] is not None:
        previous, op_id = parents[cursor] or (cursor, "")
        witness.append(op_id)
        cursor = previous
    witness.reverse()
    return witness


def generate_numeric_machine_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = _difficulty(difficulty)
    rng = _rng(seed, NUMERIC_MACHINE)
    reachable = _is_reachable_seed(seed, NUMERIC_MACHINE)
    modulus = rng.randint(3 + difficulty, 6 + 2 * difficulty)
    span = modulus * (18 + difficulty * 3)
    lower, upper = -span, span

    increments = [modulus, -modulus]
    if difficulty >= 3:
        increments.append(rng.choice((-2, 2)) * modulus)
    ops = [
        {
            "id": f"op{index + 1}",
            "label": (
                f"x ↦ x − {abs(increment)}"
                if increment < 0
                else f"x ↦ x + {increment}"
            ),
            "spec": {"kind": "affine", "a": 1, "b": increment},
        }
        for index, increment in enumerate(increments)
    ]

    start_value = rng.randint(-2, 2) * modulus + rng.randrange(modulus)
    distances, parents = _bfs_numeric(
        start=start_value,
        ops=ops,
        lower=lower,
        upper=upper,
    )
    witness: list[str] | None
    certificate: dict[str, Any] | None
    if reachable:
        minimum, maximum = DISTANCE_RANGES[difficulty]
        candidates = sorted(
            value
            for value, distance in distances.items()
            if minimum <= distance <= maximum
        )
        if not candidates:
            raise RuntimeError("Numeric machine has no target in the requested range")
        target_value = rng.choice(candidates)
        witness = _restore_scalar_witness(target_value, parents)
        certificate = None
    else:
        target_candidates = [
            value
            for value in range(lower, upper + 1)
            if value % modulus != start_value % modulus
        ]
        target_value = rng.choice(target_candidates)
        witness = None
        certificate = {
            "kind": "residue_mod",
            "modulus": modulus,
            "start_residue": start_value % modulus,
            "target_residue": target_value % modulus,
        }

    start = {"value": start_value}
    target = {"value": target_value}
    public = _base_public(
        kind=MACHINE_PANEL_KIND,
        sub_kind=NUMERIC_MACHINE,
        prompt=(
            "Получите целое число на целевом экране с помощью показанных "
            "операций или укажите, что цель недостижима."
        ),
        ops=ops,
        start=start,
        target=target,
    )
    public["working_range"] = {"min": lower, "max": upper}
    private = _initial_private(
        sub_kind=NUMERIC_MACHINE,
        difficulty=difficulty,
        reachable=reachable,
        start=start,
        target=target,
        witness=witness,
        certificate=certificate,
    )
    return public, private


def _cycle_permutation(n: int, cycle: tuple[int, ...]) -> tuple[int, ...]:
    permutation = list(range(n))
    for source, destination in zip(cycle, (*cycle[1:], cycle[0])):
        permutation[destination] = source
    return tuple(permutation)


def _permutation_parity(values: Iterable[int]) -> int:
    items = list(values)
    inversions = sum(
        items[left] > items[right]
        for left in range(len(items))
        for right in range(left + 1, len(items))
    )
    return inversions % 2


def _apply_permutation(values: tuple[int, ...], mapping: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(values[mapping[index]] for index in range(len(values)))


def _bfs_permutations(
    *,
    start: tuple[int, ...],
    ops: list[Operation],
) -> tuple[
    dict[tuple[int, ...], int],
    dict[tuple[int, ...], tuple[tuple[int, ...], str] | None],
]:
    mappings = {
        str(op["id"]): tuple(int(item) for item in op["spec"]["mapping"])
        for op in ops
    }
    distances = {start: 0}
    parents: dict[
        tuple[int, ...], tuple[tuple[int, ...], str] | None
    ] = {start: None}
    queue: deque[tuple[int, ...]] = deque([start])
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


def _restore_permutation_witness(
    target: tuple[int, ...],
    parents: dict[
        tuple[int, ...], tuple[tuple[int, ...], str] | None
    ],
) -> list[str]:
    witness: list[str] = []
    cursor = target
    while parents[cursor] is not None:
        previous, op_id = parents[cursor] or (cursor, "")
        witness.append(op_id)
        cursor = previous
    witness.reverse()
    return witness


def generate_perm_puzzle_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = _difficulty(difficulty)
    rng = _rng(seed, PERM_PUZZLE)
    reachable = _is_reachable_seed(seed, PERM_PUZZLE)
    n = 5 if difficulty == 1 else 6

    labels = list(range(n))
    rng.shuffle(labels)
    relabel = tuple(labels)
    first_cycle = tuple(relabel[index] for index in (0, 1, 2))
    second_indices = (1, 2, 3, 4, 5) if n == 6 else (0, 1, 2, 3, 4)
    second_cycle = tuple(relabel[index] for index in second_indices)
    mappings = (
        _cycle_permutation(n, first_cycle),
        _cycle_permutation(n, second_cycle),
    )
    if any(_permutation_parity(mapping) != 0 for mapping in mappings):
        raise RuntimeError("Permutation machine operations must remain even")
    ops = [
        {
            "id": f"op{index + 1}",
            "label": f"Перестановка {chr(1040 + index)}",
            "spec": {
                "kind": "reorder",
                "mapping": list(mapping),
            },
        }
        for index, mapping in enumerate(mappings)
    ]

    start_tuple = tuple(rng.sample(range(n), n))
    distances, parents = _bfs_permutations(start=start_tuple, ops=ops)
    witness: list[str] | None
    certificate: dict[str, Any] | None
    if reachable:
        minimum, maximum = DISTANCE_RANGES[difficulty]
        candidates = sorted(
            state
            for state, distance in distances.items()
            if minimum <= distance <= maximum
        )
        if not candidates:
            farthest = max(distances.values())
            candidates = sorted(
                state for state, distance in distances.items() if distance == farthest
            )
        target_tuple = rng.choice(candidates)
        witness = _restore_permutation_witness(target_tuple, parents)
        certificate = None
    else:
        opposite_parity = 1 - _permutation_parity(start_tuple)
        candidates = [
            permutation
            for permutation in _all_permutations(n)
            if _permutation_parity(permutation) == opposite_parity
        ]
        target_tuple = rng.choice(candidates)
        witness = None
        certificate = {
            "kind": "permutation_parity",
            "start_parity": _permutation_parity(start_tuple),
            "target_parity": _permutation_parity(target_tuple),
        }

    start = {"cards": [value + 1 for value in start_tuple]}
    target = {"cards": [value + 1 for value in target_tuple]}
    public = _base_public(
        kind=MACHINE_PANEL_KIND,
        sub_kind=PERM_PUZZLE,
        prompt=(
            "Переставьте карточки в целевой порядок с помощью двух показанных "
            "операций или укажите, что это невозможно."
        ),
        ops=ops,
        start=start,
        target=target,
    )
    public["card_count"] = n
    private = _initial_private(
        sub_kind=PERM_PUZZLE,
        difficulty=difficulty,
        reachable=reachable,
        start=start,
        target=target,
        witness=witness,
        certificate=certificate,
    )
    return public, private


def _all_permutations(n: int) -> list[tuple[int, ...]]:
    # Local iterative implementation avoids importing itertools into the hot
    # generator path and is still bounded by 6! = 720 states.
    result: list[tuple[int, ...]] = [()]
    for value in range(n):
        result = [
            (*prefix[:index], value, *prefix[index:])
            for prefix in result
            for index in range(len(prefix) + 1)
        ]
    return result


def _leaper_vectors(a: int, b: int) -> tuple[tuple[int, int], ...]:
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
    point: tuple[int, int],
    *,
    rows: int,
    cols: int,
    blocked: frozenset[tuple[int, int]],
    vectors: tuple[tuple[int, int], ...],
) -> tuple[tuple[int, int], ...]:
    row, col = point
    return tuple(
        sorted(
            (row + row_delta, col + col_delta)
            for row_delta, col_delta in vectors
            if _inside(row + row_delta, col + col_delta, rows, cols)
            and (row + row_delta, col + col_delta) not in blocked
        )
    )


def _bfs_leaper(
    *,
    start: tuple[int, int],
    rows: int,
    cols: int,
    blocked: frozenset[tuple[int, int]],
    vectors: tuple[tuple[int, int], ...],
) -> tuple[
    dict[tuple[int, int], int],
    dict[tuple[int, int], tuple[tuple[int, int], str] | None],
]:
    vector_ids = {
        vector: f"op{index + 1}" for index, vector in enumerate(vectors)
    }
    distances = {start: 0}
    parents: dict[
        tuple[int, int], tuple[tuple[int, int], str] | None
    ] = {start: None}
    queue: deque[tuple[int, int]] = deque([start])
    while queue:
        current = queue.popleft()
        for destination in _leaper_neighbors(
            current,
            rows=rows,
            cols=cols,
            blocked=blocked,
            vectors=vectors,
        ):
            if destination in distances:
                continue
            delta = (
                destination[0] - current[0],
                destination[1] - current[1],
            )
            distances[destination] = distances[current] + 1
            parents[destination] = (current, vector_ids[delta])
            queue.append(destination)
    return distances, parents


def _restore_leaper_witness(
    target: tuple[int, int],
    parents: dict[
        tuple[int, int], tuple[tuple[int, int], str] | None
    ],
) -> list[str]:
    witness: list[str] = []
    cursor = target
    while parents[cursor] is not None:
        previous, op_id = parents[cursor] or (cursor, "")
        witness.append(op_id)
        cursor = previous
    witness.reverse()
    return witness


def _point_state(point: tuple[int, int]) -> State:
    return {"row": point[0], "col": point[1]}


def _public_chess_board(
    *,
    rows: int,
    cols: int,
    blocked: Iterable[tuple[int, int]],
    current: tuple[int, int],
    target: tuple[int, int],
) -> list[list[str | None]]:
    blocked_set = set(blocked)
    board: list[list[str | None]] = []
    for row in range(rows - 1, -1, -1):
        rendered_row: list[str | None] = []
        for col in range(cols):
            point = (row, col)
            if point == current:
                rendered_row.append("wN")
            elif point == target:
                rendered_row.append("bK")
            elif point in blocked_set:
                rendered_row.append("bP")
            else:
                rendered_row.append(None)
        board.append(rendered_row)
    return board


def generate_leaper_board_task(
    *,
    seed: int,
    difficulty: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    difficulty = _difficulty(difficulty)
    rng = _rng(seed, LEAPER_BOARD)
    reachable = _is_reachable_seed(seed, LEAPER_BOARD)
    rows = cols = 6 if difficulty == 1 else 7 if difficulty <= 3 else 8
    minimum, maximum = DISTANCE_RANGES[difficulty]
    jump_catalog = [(1, 1), (0, 2), (1, 3)]

    chosen: tuple[
        frozenset[tuple[int, int]],
        tuple[tuple[int, int], ...],
        tuple[int, int],
        tuple[int, int],
        list[str] | None,
        tuple[int, int],
    ] | None = None
    points = [(row, col) for row in range(rows) for col in range(cols)]
    for attempt in range(MAX_GENERATION_ATTEMPTS):
        # The diagonal step is used more often at high difficulty because
        # obstacles can form long, still understandable routes.
        a, b = (
            (1, 1)
            if difficulty >= 4 or attempt >= MAX_GENERATION_ATTEMPTS // 2
            else rng.choice(jump_catalog)
        )
        vectors = _leaper_vectors(a, b)
        obstacle_ratio = rng.uniform(0.12, 0.30)
        blocked = frozenset(
            point for point in points if rng.random() < obstacle_ratio
        )
        free = [point for point in points if point not in blocked]
        if len(free) < 8:
            continue
        rng.shuffle(free)

        for start_point in free:
            if not _leaper_neighbors(
                start_point,
                rows=rows,
                cols=cols,
                blocked=blocked,
                vectors=vectors,
            ):
                continue
            distances, parents = _bfs_leaper(
                start=start_point,
                rows=rows,
                cols=cols,
                blocked=blocked,
                vectors=vectors,
            )
            if reachable:
                candidates = sorted(
                    point
                    for point, distance in distances.items()
                    if minimum <= distance <= maximum
                )
                if not candidates:
                    continue
                target_point = rng.choice(candidates)
                witness = _restore_leaper_witness(target_point, parents)
            else:
                # All catalog jumps have even a+b, so checkerboard colour is
                # an exact, human-readable invariant.
                candidates = sorted(
                    point
                    for point in free
                    if (point[0] + point[1]) % 2
                    != (start_point[0] + start_point[1]) % 2
                )
                if not candidates:
                    continue
                target_point = rng.choice(candidates)
                witness = None
            chosen = (
                blocked,
                vectors,
                start_point,
                target_point,
                witness,
                (a, b),
            )
            break
        if chosen is not None:
            break

    if chosen is None:
        raise RuntimeError("Unable to generate a non-degenerate leaper board")
    blocked, vectors, start_point, target_point, witness, jump = chosen
    ops = [
        {
            "id": f"op{index + 1}",
            "label": f"Прыжок ({row_delta:+d}, {col_delta:+d})",
            "spec": {
                "kind": "leap",
                "row_delta": row_delta,
                "col_delta": col_delta,
            },
        }
        for index, (row_delta, col_delta) in enumerate(vectors)
    ]
    start = _point_state(start_point)
    target = _point_state(target_point)
    certificate = (
        None
        if reachable
        else {
            "kind": "checkerboard_parity",
            "start_parity": (start_point[0] + start_point[1]) % 2,
            "target_parity": (target_point[0] + target_point[1]) % 2,
            "jump_sum_parity": (jump[0] + jump[1]) % 2,
        }
    )
    public = _base_public(
        kind=CHESS_KIND,
        sub_kind=LEAPER_BOARD,
        prompt=(
            "Переведите фигуру на отмеченную клетку разрешёнными прыжками. "
            "Клетки с препятствиями недоступны."
        ),
        ops=ops,
        start=start,
        target=target,
    )
    public.update(
        {
            "rows": rows,
            "cols": cols,
            "blocked": [
                _point_state(point) for point in sorted(blocked)
            ],
            "jump": {"a": jump[0], "b": jump[1]},
            "board": _public_chess_board(
                rows=rows,
                cols=cols,
                blocked=blocked,
                current=start_point,
                target=target_point,
            ),
        }
    )
    private = _initial_private(
        sub_kind=LEAPER_BOARD,
        difficulty=difficulty,
        reachable=reachable,
        start=start,
        target=target,
        witness=witness,
        certificate=certificate,
    )
    return public, private


GENERATORS: dict[
    str,
    Callable[..., tuple[dict[str, Any], dict[str, Any]]],
] = {
    LAMPS_GF2: generate_lamps_gf2_task,
    NUMERIC_MACHINE: generate_numeric_machine_task,
    PERM_PUZZLE: generate_perm_puzzle_task,
    LEAPER_BOARD: generate_leaper_board_task,
}


def generate_machine_reach_task(
    *,
    seed: int,
    difficulty: int,
    sub_kind: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Generate one deterministic task.

    When ``sub_kind`` is omitted it is selected deterministically from the
    task seed, allowing the registry to expose one family with four variants.
    """

    selected = sub_kind or SUB_KINDS[seed % len(SUB_KINDS)]
    try:
        generator = GENERATORS[selected]
    except KeyError as error:
        raise ValueError(f"Unsupported machine sub-kind: {selected!r}") from error
    return generator(seed=seed, difficulty=difficulty)


def _operation(public_state: dict[str, Any], op_id: str) -> Operation | None:
    return next(
        (
            op
            for op in public_state.get("ops", [])
            if isinstance(op, dict) and op.get("id") == op_id
        ),
        None,
    )


def _apply_operation(
    *,
    sub_kind: str,
    state: State,
    operation: Operation,
    public_state: dict[str, Any],
) -> State | None:
    spec = operation["spec"]
    if sub_kind == LAMPS_GF2:
        lamps = [int(value) for value in state["lamps"]]
        for index in spec["indices"]:
            lamps[int(index)] ^= 1
        return {"lamps": lamps}
    if sub_kind == NUMERIC_MACHINE:
        bounds = public_state["working_range"]
        result = _numeric_next(
            int(state["value"]),
            spec,
            int(bounds["min"]),
            int(bounds["max"]),
        )
        return None if result is None else {"value": result}
    if sub_kind == PERM_PUZZLE:
        zero_based = tuple(int(value) - 1 for value in state["cards"])
        mapping = tuple(int(value) for value in spec["mapping"])
        result = _apply_permutation(zero_based, mapping)
        return {"cards": [value + 1 for value in result]}
    if sub_kind == LEAPER_BOARD:
        row = int(state["row"]) + int(spec["row_delta"])
        col = int(state["col"]) + int(spec["col_delta"])
        blocked = {
            (int(point["row"]), int(point["col"]))
            for point in public_state["blocked"]
        }
        if not _inside(row, col, int(public_state["rows"]), int(public_state["cols"])):
            return None
        if (row, col) in blocked:
            return None
        return {"row": row, "col": col}
    raise ValueError(f"Unsupported machine sub-kind: {sub_kind!r}")


def _refresh_dynamic_public(
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> None:
    public_state["current"] = deepcopy(private_state["current"])
    public_state["steps_taken"] = int(
        private_state["interaction"]["apply_count"]
    )
    if private_state["sub_kind"] == LEAPER_BOARD:
        current = private_state["current"]
        target = private_state["target"]
        public_state["board"] = _public_chess_board(
            rows=int(public_state["rows"]),
            cols=int(public_state["cols"]),
            blocked=(
                (int(point["row"]), int(point["col"]))
                for point in public_state["blocked"]
            ),
            current=(int(current["row"]), int(current["col"])),
            target=(int(target["row"]), int(target["col"])),
        )


def transition_machine_action(
    *,
    action_type: str,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
    client_action_id: str,
    op_id: str | None = None,
    first_action_latency_ms: int | None = None,
) -> MachineTransition:
    """Apply or undo one operation without mutating the supplied states.

    The transition itself is idempotent.  Replaying a ``client_action_id`` with
    the same payload returns the already-materialized state unchanged; reusing
    it for another payload raises ``ValueError``.
    """

    normalized_type = action_type.strip().casefold()
    if normalized_type not in {"apply_op", "undo"}:
        raise ValueError("Machine action_type must be 'apply_op' or 'undo'")
    normalized_op = (op_id or "").strip()
    if normalized_type == "apply_op" and not normalized_op:
        raise ValueError("apply_op requires op_id")
    normalized_input = (
        f"apply_op:{normalized_op}" if normalized_type == "apply_op" else "undo"
    )
    action_id = client_action_id.strip()
    if not action_id:
        raise ValueError("client_action_id must not be empty")

    next_public = deepcopy(public_state)
    next_private = deepcopy(private_state)
    interaction = next_private["interaction"]
    processed = interaction["processed_actions"]
    previous = processed.get(action_id)
    if previous is not None:
        if previous["normalized_input"] != normalized_input:
            raise ValueError("client_action_id was reused with another action")
        return MachineTransition(
            public_state=next_public,
            private_state=next_private,
            accepted=bool(previous["accepted"]),
            completed=False,
            goal_reached=next_private["current"] == next_private["target"],
            reason=str(previous["reason"]),
            message=str(previous["message"]),
            normalized_input=normalized_input,
        )

    if (
        interaction["first_action_latency_ms"] is None
        and first_action_latency_ms is not None
    ):
        interaction["first_action_latency_ms"] = max(
            0, int(first_action_latency_ms)
        )

    accepted = False
    if normalized_type == "apply_op":
        operation = _operation(next_public, normalized_op)
        if operation is None:
            reason = "unknown_operation"
            message = "Операция не распознана. Состояние не изменилось."
        else:
            result = _apply_operation(
                sub_kind=str(next_private["sub_kind"]),
                state=next_private["current"],
                operation=operation,
                public_state=next_public,
            )
            if result is None:
                reason = "operation_unavailable"
                message = "Операция сейчас неприменима. Состояние не изменилось."
            elif result == next_private["current"]:
                reason = "no_effect"
                message = "Операция не меняет состояние."
            else:
                accepted = True
                reason = "applied"
                message = "Операция применена."
                next_private["history"].append(deepcopy(next_private["current"]))
                next_private["current"] = result
                interaction["apply_count"] = int(interaction["apply_count"]) + 1
                result_key = _state_key(result)
                if result_key in interaction["visited_state_keys"]:
                    interaction["revisited_count"] = (
                        int(interaction["revisited_count"]) + 1
                    )
                else:
                    interaction["visited_state_keys"].append(result_key)
    else:
        if not next_private["history"]:
            reason = "nothing_to_undo"
            message = "Отменять нечего. Состояние не изменилось."
        else:
            accepted = True
            reason = "undone"
            message = "Последняя операция отменена."
            next_private["current"] = next_private["history"].pop()
            interaction["undo_count"] = int(interaction["undo_count"]) + 1

    processed[action_id] = {
        "normalized_input": normalized_input,
        "accepted": accepted,
        "reason": reason,
        "message": message,
    }
    _refresh_dynamic_public(next_public, next_private)
    return MachineTransition(
        public_state=next_public,
        private_state=next_private,
        accepted=accepted,
        completed=False,
        goal_reached=next_private["current"] == next_private["target"],
        reason=reason,
        message=message,
        normalized_input=normalized_input,
    )


def telemetry_aggregates(private_state: dict[str, Any]) -> dict[str, Any]:
    interaction = private_state.get("interaction") or {}
    apply_count = int(interaction.get("apply_count") or 0)
    min_len_value = private_state.get("min_len")
    min_len = (
        int(min_len_value)
        if isinstance(min_len_value, int) and not isinstance(min_len_value, bool)
        else None
    )
    return {
        "first_action_latency_ms": interaction.get("first_action_latency_ms"),
        "undo_count": int(interaction.get("undo_count") or 0),
        "revisited_states": (
            int(interaction.get("revisited_count") or 0) / apply_count
            if apply_count
            else 0.0
        ),
        # len_ratio is actual/minimal; 1 is optimal and larger is less efficient.
        "len_ratio": (
            apply_count / min_len if min_len is not None and min_len > 0 else None
        ),
        "actual_length": apply_count,
    }


def evaluate_machine_answer(
    *,
    answer: str,
    private_state: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate ``done``/``impossible`` and return API integration hints."""

    normalized = answer.strip().casefold()
    done_answers = {"done", "готово", "готов"}
    impossible_answers = {"impossible", "недостижимо", "невозможно"}
    aggregates = telemetry_aggregates(private_state)
    base = {
        "family": FAMILY_KEY,
        "generator_version": GENERATOR_VERSION,
        "difficulty": int(private_state["difficulty"]),
        **aggregates,
    }
    if normalized in done_answers:
        if private_state["current"] != private_state["target"]:
            return {
                **base,
                "accepted": False,
                "correct": False,
                "should_finalize": False,
                "evidence": 0,
                "continuous_score": 0.0,
                "false_impossible": False,
                "freeze_seconds": 0,
                "reason": "not_at_target",
                "feedback": "Задача ещё не завершена.",
            }
        min_len = int(private_state["min_len"])
        actual_length = max(min_len, int(aggregates["actual_length"]))
        continuous_score = min(
            1.0,
            0.6 + 0.4 * min_len / actual_length,
        )
        return {
            **base,
            "accepted": True,
            "correct": True,
            "should_finalize": True,
            "evidence": 1,
            "continuous_score": continuous_score,
            "false_impossible": False,
            "freeze_seconds": 0,
            "reason": "target_reached",
            "feedback": "Ответ принят.",
        }
    if normalized in impossible_answers:
        correct = not bool(private_state["reachable"])
        return {
            **base,
            "accepted": correct,
            "correct": correct,
            "should_finalize": correct,
            "evidence": 1 if correct else 0,
            "continuous_score": 1.0 if correct else 0.0,
            "false_impossible": not correct,
            "freeze_seconds": 0 if correct else 15,
            "reason": "correct_impossible" if correct else "false_impossible",
            "feedback": (
                "Ответ принят."
                if correct
                else "Ответ не принят. Повторите попытку через 15 секунд."
            ),
        }
    return {
        **base,
        "accepted": False,
        "correct": False,
        "should_finalize": False,
        "evidence": 0,
        "continuous_score": 0.0,
        "false_impossible": False,
        "freeze_seconds": 0,
        "reason": "invalid_answer",
        "feedback": "Используйте ответ done или impossible.",
    }


def simulate_witness(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> State | None:
    witness = private_state.get("witness")
    if not isinstance(witness, list):
        return None
    state = deepcopy(private_state["start"])
    for op_id in witness:
        operation = _operation(public_state, str(op_id))
        if operation is None:
            return None
        result = _apply_operation(
            sub_kind=str(private_state["sub_kind"]),
            state=state,
            operation=operation,
            public_state=public_state,
        )
        if result is None:
            return None
        state = result
    return state


def shortest_witness(
    *,
    public_state: dict[str, Any],
    start: State | None = None,
    target: State | None = None,
) -> list[str] | None:
    """Return an exact shortest operation sequence in the finite state graph."""

    initial = deepcopy(start if start is not None else public_state["start"])
    goal = target if target is not None else public_state["target"]
    if initial == goal:
        return []
    sub_kind = str(public_state["sub_kind"])
    queue: deque[State] = deque([initial])
    start_key = _state_key(initial)
    parents: dict[str, tuple[str, str] | None] = {start_key: None}
    states: dict[str, State] = {start_key: initial}
    goal_key: str | None = None
    while queue:
        current = queue.popleft()
        current_key = _state_key(current)
        for operation in public_state["ops"]:
            result = _apply_operation(
                sub_kind=sub_kind,
                state=current,
                operation=operation,
                public_state=public_state,
            )
            if result is None:
                continue
            result_key = _state_key(result)
            if result_key in parents:
                continue
            parents[result_key] = (current_key, str(operation["id"]))
            states[result_key] = result
            if result == goal:
                goal_key = result_key
                queue.clear()
                break
            queue.append(result)
    if goal_key is None:
        return None
    witness: list[str] = []
    cursor = goal_key
    while parents[cursor] is not None:
        previous, op_id = parents[cursor] or (cursor, "")
        witness.append(op_id)
        cursor = previous
    witness.reverse()
    return witness


def validate_unreachable_certificate(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> bool:
    certificate = private_state.get("certificate")
    if private_state.get("reachable") is not False or not isinstance(certificate, dict):
        return False
    kind = certificate.get("kind")
    start = private_state["start"]
    target = private_state["target"]

    if kind == "gf2_orthogonal_vector":
        vector = _from_bits(certificate["vector"])
        start_value = _from_bits(start["lamps"])
        target_value = _from_bits(target["lamps"])
        operation_vectors = [
            sum(1 << int(index) for index in op["spec"]["indices"])
            for op in public_state["ops"]
        ]
        return (
            all(
                (vector & operation).bit_count() % 2 == 0
                for operation in operation_vectors
            )
            and (vector & start_value).bit_count() % 2
            != (vector & target_value).bit_count() % 2
        )
    if kind == "residue_mod":
        modulus = int(certificate["modulus"])
        return (
            modulus > 1
            and all(
                int(op["spec"]["a"]) % modulus == 1 % modulus
                and int(op["spec"]["b"]) % modulus == 0
                for op in public_state["ops"]
            )
            and int(start["value"]) % modulus != int(target["value"]) % modulus
        )
    if kind == "permutation_parity":
        start_values = [int(value) for value in start["cards"]]
        target_values = [int(value) for value in target["cards"]]
        return (
            all(
                _permutation_parity(op["spec"]["mapping"]) == 0
                for op in public_state["ops"]
            )
            and _permutation_parity(start_values)
            != _permutation_parity(target_values)
        )
    if kind == "checkerboard_parity":
        vectors_preserve_colour = all(
            (
                int(op["spec"]["row_delta"])
                + int(op["spec"]["col_delta"])
            )
            % 2
            == 0
            for op in public_state["ops"]
        )
        return (
            vectors_preserve_colour
            and (int(start["row"]) + int(start["col"])) % 2
            != (int(target["row"]) + int(target["col"])) % 2
        )
    if kind == "disconnected_component" and private_state["sub_kind"] == LEAPER_BOARD:
        blocked = frozenset(
            (int(point["row"]), int(point["col"]))
            for point in public_state["blocked"]
        )
        vectors = tuple(
            (
                int(op["spec"]["row_delta"]),
                int(op["spec"]["col_delta"]),
            )
            for op in public_state["ops"]
        )
        distances, _parents = _bfs_leaper(
            start=(int(start["row"]), int(start["col"])),
            rows=int(public_state["rows"]),
            cols=int(public_state["cols"]),
            blocked=blocked,
            vectors=vectors,
        )
        return (int(target["row"]), int(target["col"])) not in distances
    return False


def validate_machine_instance(
    *,
    public_state: dict[str, Any],
    private_state: dict[str, Any],
) -> bool:
    """Validate public/private consistency and the solver proof."""

    if public_state.get("sub_kind") != private_state.get("sub_kind"):
        return False
    if public_state.get("start") != private_state.get("start"):
        return False
    if public_state.get("target") != private_state.get("target"):
        return False
    if private_state.get("start") == private_state.get("target"):
        return False
    if private_state.get("reachable"):
        witness = private_state.get("witness")
        exact_witness = shortest_witness(public_state=public_state)
        return (
            isinstance(witness, list)
            and len(witness) == private_state.get("min_len")
            and len(witness) >= 2
            and exact_witness is not None
            and len(exact_witness) == len(witness)
            and simulate_witness(
                public_state=public_state,
                private_state=private_state,
            )
            == private_state.get("target")
            and private_state.get("certificate") is None
        )
    return (
        private_state.get("witness") is None
        and private_state.get("min_len") is None
        and validate_unreachable_certificate(
            public_state=public_state,
            private_state=private_state,
        )
    )
