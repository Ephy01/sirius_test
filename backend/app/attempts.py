"""Lifecycle of an attempt: activity, expiry and seeds."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .dependencies import api_error
from .events import append_event
from .models import Attempt, AttemptEvent, AttemptStatus, Contest, Enrollment, as_utc, utc_now
from .schemas import ClientTelemetryRequest

CLIENT_TELEMETRY_GRACE_PERIOD = timedelta(minutes=5)
CLIENT_TELEMETRY_CLOCK_SKEW = timedelta(minutes=2)


def expire_attempt_if_needed(session: Session, attempt: Attempt, now: datetime) -> bool:
    if attempt.status != AttemptStatus.ACTIVE or as_utc(attempt.deadline_at) > now:
        return False
    updated = session.execute(
        update(Attempt)
        .where(Attempt.id == attempt.id, Attempt.status == AttemptStatus.ACTIVE, Attempt.deadline_at <= now)
        .values(status=AttemptStatus.EXPIRED, active_slot=None, finished_at=now)
        .execution_options(synchronize_session=False)
    )
    if updated.rowcount != 1:
        session.expire(attempt)
        session.refresh(attempt)
        return False
    attempt.status = AttemptStatus.EXPIRED
    attempt.active_slot = None
    attempt.finished_at = now
    append_event(
        session,
        attempt_id=attempt.id,
        event_type='attempt_expired',
        payload={'deadline_at': as_utc(attempt.deadline_at).isoformat()},
    )
    return True


def expire_stale_attempts(session: Session, attempts: list[Attempt]) -> None:
    now = utc_now()
    if any([expire_attempt_if_needed(session, attempt, now) for attempt in attempts]):
        session.commit()


def active_attempt(session: Session, enrollment_id: str, *, lock: bool = False) -> Attempt | None:
    statement = select(Attempt).where(
        Attempt.enrollment_id == enrollment_id, Attempt.status == AttemptStatus.ACTIVE
    )
    if lock:
        statement = statement.with_for_update()
    attempt = session.scalar(statement)
    if attempt is None:
        return None
    if expire_attempt_if_needed(session, attempt, utc_now()):
        session.commit()
        return None
    return attempt if attempt.status == AttemptStatus.ACTIVE else None


def require_active_attempt(session: Session, enrollment: Enrollment) -> Attempt:
    attempt = active_attempt(session, enrollment.id, lock=True)
    if attempt is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'ACTIVE_ATTEMPT_REQUIRED',
            'Сначала запустите попытку. Истёкшую попытку продолжить нельзя.',
        )
    return attempt


def telemetry_attempt(session: Session, enrollment: Enrollment, payload: ClientTelemetryRequest) -> Attempt:
    """Attempt a client event belongs to, with a short delivery grace period.

    The browser may create an event before the deadline and deliver it a few
    seconds later after a network failure. Task actions still require an active
    attempt; only client telemetry gets this narrow window.
    """

    attempt = _find_telemetry_attempt(session, enrollment, payload)
    if attempt is None:
        raise api_error(status.HTTP_409_CONFLICT, 'ACTIVE_ATTEMPT_REQUIRED', 'Сначала запустите попытку.')
    if attempt.status == AttemptStatus.ACTIVE:
        return attempt

    started_at = as_utc(attempt.started_at)
    deadline = as_utc(attempt.deadline_at)
    finished_at = as_utc(attempt.finished_at) if attempt.finished_at is not None else deadline
    telemetry_end = min(deadline, finished_at)
    timestamp = as_utc(payload.client_timestamp) if payload.client_timestamp is not None else None
    allowed_elapsed_ms = int(
        (telemetry_end - started_at + CLIENT_TELEMETRY_CLOCK_SKEW).total_seconds() * 1_000
    )
    delivered_in_time = (
        utc_now() <= telemetry_end + CLIENT_TELEMETRY_GRACE_PERIOD
        and timestamp is not None
        and payload.client_elapsed_ms is not None
        and started_at - CLIENT_TELEMETRY_CLOCK_SKEW
        <= timestamp
        <= telemetry_end + CLIENT_TELEMETRY_CLOCK_SKEW
        and payload.client_elapsed_ms <= max(0, allowed_elapsed_ms)
    )
    if not delivered_in_time:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'TELEMETRY_WINDOW_CLOSED',
            'Окно приёма телеметрии этой попытки закрыто.',
        )
    return attempt


def _find_telemetry_attempt(
    session: Session, enrollment: Enrollment, payload: ClientTelemetryRequest
) -> Attempt | None:
    if payload.attempt_id is None:
        attempt = active_attempt(session, enrollment.id, lock=True)
        if attempt is not None:
            return attempt
        return session.scalar(
            select(Attempt)
            .where(Attempt.enrollment_id == enrollment.id)
            .order_by(Attempt.number.desc())
            .limit(1)
            .with_for_update()
        )
    attempt = session.scalar(
        select(Attempt)
        .where(Attempt.id == payload.attempt_id, Attempt.enrollment_id == enrollment.id)
        .with_for_update()
    )
    if attempt is None:
        raise api_error(status.HTTP_404_NOT_FOUND, 'ATTEMPT_NOT_FOUND', 'Попытка не найдена.')
    if expire_attempt_if_needed(session, attempt, utc_now()):
        session.commit()
    return attempt


def task_config_of(contest: Contest) -> dict:
    return contest.task_config if isinstance(contest.task_config, dict) else {}


def attempt_seed(contest: Contest, attempt_number: int) -> int:
    """Random seed, or a reproducible one when the contest sets ``cohort_seed``."""

    cohort_seed = task_config_of(contest).get('cohort_seed')
    if cohort_seed is None or isinstance(cohort_seed, (dict, list, bool)):
        return secrets.randbits(63)
    identity = json.dumps(
        ['cohort-attempt-v1', str(cohort_seed), attempt_number], ensure_ascii=True, separators=(',', ':')
    ).encode('ascii')
    return int.from_bytes(hashlib.sha256(identity).digest()[:8], byteorder='big') & ((1 << 63) - 1)


def attempt_task_config(session: Session, attempt: Attempt, contest: Contest) -> dict:
    """Task settings frozen when the attempt started, so later edits do not affect it."""

    started = session.scalar(
        select(AttemptEvent)
        .where(AttemptEvent.attempt_id == attempt.id, AttemptEvent.event_type == 'attempt_started')
        .order_by(AttemptEvent.sequence)
        .limit(1)
    )
    payload = started.payload if started is not None and isinstance(started.payload, dict) else {}
    snapshot = payload.get('task_config_snapshot')
    return snapshot if isinstance(snapshot, dict) else task_config_of(contest)
