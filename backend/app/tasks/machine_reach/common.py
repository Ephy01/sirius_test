"""Shared constants, seeding and state skeletons of the ``machine_reach`` sub-kinds."""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Hashable
from copy import deepcopy
from typing import Any

from ..family import State

FAMILY_KEY = 'machine_reach'
GENERATOR_VERSION = 'machine-reach-v2'
READABLE_VERSIONS = ('machine-reach-v1',)
REACHABLE_SHARE = 0.5
MACHINE_PANEL_KIND = 'machine_panel'
CHESS_KIND = 'chess'

LAMPS_GF2 = 'lamps_gf2'
NUMERIC_MACHINE = 'numeric_machine'
PERM_PUZZLE = 'perm_puzzle'
LEAPER_BOARD = 'leaper_board'
SUB_KINDS = (LAMPS_GF2, NUMERIC_MACHINE, PERM_PUZZLE, LEAPER_BOARD)

STEPS_SOFT_CAP = 24
MAX_GENERATION_ATTEMPTS = 128

Operation = dict[str, Any]

DISTANCE_RANGES: dict[int, tuple[int, int]] = {1: (2, 3), 2: (3, 5), 3: (4, 7), 4: (6, 9), 5: (8, 12)}


def checked_difficulty(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 5:
        raise ValueError('Machine difficulty must be an integer from 1 to 5')
    return value


def seeded_rng(seed: int, namespace: str) -> random.Random:
    digest = hashlib.sha256(f'{GENERATOR_VERSION}:{namespace}:{seed}'.encode('ascii')).digest()
    return random.Random(int.from_bytes(digest[:16], 'big'))


def is_reachable_seed(seed: int, sub_kind: str) -> bool:
    """Whether the target is reachable, decided independently of how the sub-kind was chosen."""

    return seeded_rng(seed, f'reachable:{sub_kind}').random() < REACHABLE_SHARE


def state_key(state: State) -> str:
    return json.dumps(state, sort_keys=True, separators=(',', ':'), ensure_ascii=True)


def operation(index: int, label: str, spec: State) -> Operation:
    return {'id': f'op{index + 1}', 'label': label, 'spec': spec}


def witness_to(target: Hashable, parents: dict[Any, tuple[Any, str] | None]) -> list[str]:
    """Operation ids along the breadth-first tree from its root to ``target``."""

    witness: list[str] = []
    cursor = target
    while (step := parents[cursor]) is not None:
        cursor, op_id = step
        witness.append(op_id)
    witness.reverse()
    return witness


def _initial_private(
    *,
    sub_kind: str,
    difficulty: int,
    start: State,
    target: State,
    witness: list[str] | None,
    certificate: State | None,
) -> State:
    return {
        'family': FAMILY_KEY,
        'generator_version': GENERATOR_VERSION,
        'sub_kind': sub_kind,
        'difficulty': difficulty,
        'reachable': witness is not None,
        'start': deepcopy(start),
        'target': deepcopy(target),
        'current': deepcopy(start),
        'witness': list(witness) if witness is not None else None,
        'min_len': len(witness) if witness is not None else None,
        'certificate': deepcopy(certificate),
        'history': [],
        'interaction': {
            'apply_count': 0,
            'undo_count': 0,
            'reset_count': 0,
            'revisited_count': 0,
            'visited_state_keys': [state_key(start)],
            'first_action_latency_ms': None,
            'processed_actions': {},
        },
    }


def _base_public(
    *, kind: str, sub_kind: str, prompt: str, ops: list[Operation], start: State, target: State
) -> State:
    return {
        'kind': kind,
        'sub_kind': sub_kind,
        'prompt': prompt,
        'ops': deepcopy(ops),
        'start': deepcopy(start),
        'target': deepcopy(target),
        'current': deepcopy(start),
        'steps_soft_cap': STEPS_SOFT_CAP,
        'steps_taken': 0,
    }


def machine_task(
    *,
    kind: str,
    sub_kind: str,
    prompt: str,
    difficulty: int,
    ops: list[Operation],
    start: State,
    target: State,
    witness: list[str] | None,
    certificate: State | None,
    extra_public: State,
) -> tuple[State, State]:
    """Public and private state of a new task; a witness exists exactly for reachable targets."""

    public = _base_public(kind=kind, sub_kind=sub_kind, prompt=prompt, ops=ops, start=start, target=target)
    public.update(extra_public)
    private = _initial_private(
        sub_kind=sub_kind,
        difficulty=difficulty,
        start=start,
        target=target,
        witness=witness,
        certificate=certificate,
    )
    return public, private
