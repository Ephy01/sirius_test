"""Common contract of a task family.

A family module builds one ``TaskFamily`` record named ``FAMILY`` and the
registry picks it up. Everything the service needs to know about a task type
lives in that record, so adding a family does not touch the API layer.

New tasks are always generated with ``version``. ``readable_versions`` lists
earlier versions whose stored tasks ``evaluate`` and ``actions`` still handle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

State = dict[str, Any]


@dataclass(frozen=True)
class Transition:
    public_state: State
    private_state: State
    accepted: bool
    reason: str
    message: str
    normalized_input: str = ''
    completed: bool = False
    evaluation_state: State | None = None


@dataclass(frozen=True)
class TaskFamily:
    key: str
    version: str
    generate: Callable[[int, int, State], tuple[State, State]]
    evaluate: Callable[[str, State], State]
    actions: dict[str, Callable[[State, State, State], Transition]] = field(default_factory=dict)
    probe_action: str | None = None
    readable_versions: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    sub_kinds: tuple[str, ...] = ()
    scripted_only: bool = False
    tracks_first_action: bool = False
    reference_answer: Callable[[State], tuple[str, list[str]]] | None = None
    debug_details: Callable[[State], list[str]] | None = None
    ai_context: Callable[[State], State] | None = None


def required_text(payload: State, key: str, message: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(message)
    return value


def optional_text(payload: State, key: str, message: str) -> str | None:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        raise ValueError(message)
    return value


def latency_ms(payload: State) -> int | None:
    value = payload.get('first_action_latency_ms')
    return value if isinstance(value, int) and not isinstance(value, bool) else None
