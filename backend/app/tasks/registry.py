"""Registry of task families.

To add a family, write a module that builds a ``TaskFamily`` named ``FAMILY``
and list the module in ``FAMILY_MODULES``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import NamedTuple

from sirius_gate.family import State, TaskFamily, Transition

from . import (
    chess_coverage,
    classic_math,
    dice_chess,
    fold_punch,
    geo_probability,
    geo_transform,
    hidden_wiring,
    machine_reach,
)
from .zendo import graph, grid, point, token


class GeneratedTask(NamedTuple):
    public_state: State
    private_state: State


# The order is the one the contest builder shows.
FAMILY_MODULES = (
    graph,
    token,
    point,
    grid,
    hidden_wiring,
    machine_reach,
    fold_punch,
    chess_coverage,
    geo_transform,
    geo_probability,
    dice_chess,
    classic_math,
)
FAMILIES: dict[str, TaskFamily] = {module.FAMILY.key: module.FAMILY for module in FAMILY_MODULES}
BUILTIN_KEYS = frozenset(FAMILIES)
ALIASES: dict[str, str] = {}
MODULE_OF: dict[str, str] = {}


def _index_aliases() -> None:
    ALIASES.clear()
    ALIASES.update(
        (alias.casefold(), family.key)
        for family in FAMILIES.values()
        for alias in (family.key, *family.aliases)
    )


_index_aliases()


def register_module_families(families: Iterable[TaskFamily], module: str) -> None:
    """Add the families of one task module; a key that is already taken rejects the whole module."""

    families = tuple(families)
    for family in families:
        if family.key in FAMILIES:
            owner = f'плагином {MODULE_OF[family.key]}' if family.key in MODULE_OF else 'платформой'
            raise ValueError(f'ключ типа задачи {family.key!r} уже занят {owner}')
    for family in families:
        FAMILIES[family.key] = family
        MODULE_OF[family.key] = module
    _index_aliases()


def unregister_module_families() -> None:
    for key in MODULE_OF:
        FAMILIES.pop(key, None)
    MODULE_OF.clear()
    _index_aliases()


def resolve_family(name: object) -> str | None:
    """Canonical family key for a name written by an organizer, if known."""

    return ALIASES.get(name.strip().casefold()) if isinstance(name, str) else None


def family_for(key: str, version: str | None = None) -> TaskFamily:
    family = FAMILIES.get(key)
    if family is None or version not in (None, family.version, *family.readable_versions):
        raise ValueError(f'Unsupported task family: {key!r}, version={version!r}')
    return family


def derive_task_seed(attempt_seed: int, ordinal: int, family: str, generator_version: str) -> int:
    """Stable 63-bit seed derived from the immutable identity of a task."""

    identity = json.dumps(
        [attempt_seed, ordinal, family, generator_version], ensure_ascii=True, separators=(',', ':')
    ).encode('ascii')
    return int.from_bytes(hashlib.sha256(identity).digest()[:8], byteorder='big') & ((1 << 63) - 1)


def generate_task(
    *, family: str, generator_version: str, seed: int, difficulty: int, context: State | None = None
) -> GeneratedTask:
    record = family_for(family, generator_version)
    if generator_version != record.version:
        raise ValueError(f'{family!r} tasks are generated only as {record.version!r}')
    return GeneratedTask(*record.generate(seed, difficulty, context or {}))


def evaluate_task(*, family: str, generator_version: str, answer: str, private_state: State) -> State:
    return family_for(family, generator_version).evaluate(answer, private_state)


def interact_task(
    *,
    family: str,
    generator_version: str,
    action_type: str,
    action_payload: State,
    public_state: State,
    private_state: State,
) -> Transition:
    action = family_for(family, generator_version).actions.get(action_type)
    if action is None:
        raise ValueError(f'Unsupported task interaction: family={family!r}, action={action_type!r}')
    return action(action_payload, public_state, private_state)


def generator_version_for(family: str) -> str:
    return family_for(family).version
