"""Append-only event log of an attempt."""

from __future__ import annotations

import hashlib
import json
import threading
import weakref

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import AttemptEvent, TaskInstance, utc_now

_SEQUENCE_LOCK = threading.Lock()
_SEQUENCE_RESERVATIONS: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def canonical_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('ascii')).hexdigest()


def next_event_sequence(session: Session, attempt_id: str) -> int:
    def current_maximum() -> int:
        stored = session.scalar(
            select(func.max(AttemptEvent.sequence)).where(AttemptEvent.attempt_id == attempt_id)
        )
        pending = [
            event.sequence
            for event in session.new
            if isinstance(event, AttemptEvent) and event.attempt_id == attempt_id
        ]
        return max([stored or 0, *pending])

    bind = session.get_bind()
    if bind.dialect.name != 'sqlite':
        return current_maximum() + 1
    # SQLite has no row locks: parallel requests reserve numbers in process memory.
    engine = getattr(bind, 'engine', bind)
    with _SEQUENCE_LOCK:
        reservations = _SEQUENCE_RESERVATIONS.setdefault(engine, {})
        sequence = max(current_maximum(), reservations.get(attempt_id, 0)) + 1
        reservations[attempt_id] = sequence
        return sequence


def append_event(
    session: Session,
    *,
    attempt_id: str,
    event_type: str,
    task_instance_id: str | None = None,
    payload: dict | None = None,
) -> AttemptEvent:
    event = AttemptEvent(
        attempt_id=attempt_id,
        task_instance_id=task_instance_id,
        event_type=event_type,
        sequence=next_event_sequence(session, attempt_id),
        payload=payload or {},
        created_at=utc_now(),
    )
    session.add(event)
    return event


def append_task_event(
    session: Session, task: TaskInstance, event_type: str, payload: dict | None = None
) -> AttemptEvent:
    return append_event(
        session, attempt_id=task.attempt_id, task_instance_id=task.id, event_type=event_type, payload=payload
    )
