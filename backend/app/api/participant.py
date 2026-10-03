import hashlib
from datetime import datetime, timedelta

from fastapi import APIRouter, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..attempts import (
    active_attempt,
    attempt_seed,
    pending_grant,
    require_active_attempt,
    task_config_of,
    telemetry_attempt,
)
from ..dependencies import ParticipantEnrollmentDependency, SessionDependency, api_error
from ..events import append_event, canonical_hash, canonical_json
from ..models import (
    Attempt,
    AttemptGrant,
    AttemptGrantStatus,
    AttemptStatus,
    ClientTelemetryReceipt,
    Contest,
    ContestStatus,
    TaskInstance,
    as_utc,
    utc_now,
)
from ..schemas import (
    AttemptStartResponse,
    ClientTelemetryRequest,
    CurrentTaskResponse,
    EnrollmentResponse,
    NextTaskResponse,
    ParticipantContextResponse,
    TaskProgressItem,
    TaskProgressResponse,
)
from ..task_flow import create_or_get_current_task, get_task_or_error

router = APIRouter(prefix='/participant')

MAX_CLIENT_EVENTS_PER_ATTEMPT = 5_000
MAX_CLIENT_EVENTS_PER_MINUTE = 240


@router.get('/context', response_model=ParticipantContextResponse)
def participant_context(
    enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> ParticipantContextResponse:
    return ParticipantContextResponse(
        contest=enrollment.contest,
        enrollment=EnrollmentResponse.model_validate(enrollment),
        participant=enrollment.participant,
        active_attempt=active_attempt(session, enrollment.id),
    )


def _receipt_of(session: Session, attempt_id: str, client_event_id: str) -> ClientTelemetryReceipt | None:
    return session.scalar(
        select(ClientTelemetryReceipt).where(
            ClientTelemetryReceipt.attempt_id == attempt_id,
            ClientTelemetryReceipt.client_event_id == client_event_id,
        )
    )


def _receipt_count(session: Session, attempt_id: str, *conditions) -> int:
    return int(
        session.scalar(
            select(func.count(ClientTelemetryReceipt.id)).where(
                ClientTelemetryReceipt.attempt_id == attempt_id, *conditions
            )
        )
        or 0
    )


def _event_id_reused():
    return api_error(
        status.HTTP_409_CONFLICT,
        'TELEMETRY_EVENT_ID_REUSED',
        'Этот идентификатор события уже использован с другими данными.',
    )


def _client_event_payload(payload: ClientTelemetryRequest) -> dict:
    return {
        'client_event_id': payload.client_event_id,
        'client_session_id': payload.client_session_id,
        'client_timestamp': as_utc(payload.client_timestamp).isoformat()
        if payload.client_timestamp is not None
        else None,
        'client_elapsed_ms': payload.client_elapsed_ms,
        'payload': payload.payload,
    }


def _event_fingerprint(event_type: str, task_id: str | None, event_payload: dict) -> str:
    return hashlib.sha256(
        canonical_json(
            {'event_type': event_type, 'task_instance_id': task_id, 'payload': event_payload}
        ).encode('utf-8')
    ).hexdigest()


def _admission_time(session: Session, attempt_id: str) -> datetime:
    """Moment a new client event is accepted, once it fits the per-attempt and per-minute limits."""

    if _receipt_count(session, attempt_id) >= MAX_CLIENT_EVENTS_PER_ATTEMPT:
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            'TELEMETRY_EVENT_LIMIT_REACHED',
            'Для этой попытки достигнут предел клиентских событий.',
        )
    received_at = utc_now()
    recent = _receipt_count(
        session, attempt_id, ClientTelemetryReceipt.created_at >= received_at - timedelta(minutes=1)
    )
    if recent >= MAX_CLIENT_EVENTS_PER_MINUTE:
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            'TELEMETRY_RATE_LIMITED',
            'Слишком много событий телеметрии. Повторите попытку позже.',
        )
    return received_at


@router.post('/telemetry', status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def record_client_telemetry(
    payload: ClientTelemetryRequest, enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> Response:
    attempt = telemetry_attempt(session, enrollment, payload)
    task_id = None
    if payload.task_id is not None:
        task_id = get_task_or_error(session, attempt, payload.task_id).id
    event_payload = _client_event_payload(payload)
    fingerprint = _event_fingerprint(payload.event_type, task_id, event_payload)
    delivered = Response(status_code=status.HTTP_204_NO_CONTENT)

    existing = _receipt_of(session, attempt.id, payload.client_event_id)
    if existing is not None:
        if existing.fingerprint != fingerprint:
            raise _event_id_reused()
        return delivered
    received_at = _admission_time(session, attempt.id)
    session.add(
        ClientTelemetryReceipt(
            attempt_id=attempt.id,
            client_event_id=payload.client_event_id,
            fingerprint=fingerprint,
            created_at=received_at,
        )
    )
    append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task_id,
        event_type=payload.event_type,
        payload=event_payload,
    )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raced = _receipt_of(session, attempt.id, payload.client_event_id)
        if raced is None:
            raise
        if raced.fingerprint != fingerprint:
            raise _event_id_reused() from None
    return delivered


def _required_grant(session: Session, enrollment_id: str) -> AttemptGrant:
    """The organizer's permission for a repeated attempt, locked until it is consumed."""

    grant = pending_grant(session, enrollment_id, lock=True)
    if grant is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'ATTEMPT_NOT_AVAILABLE',
            'Для новой попытки требуется разрешение организатора.',
        )
    return grant


def _consume_grant(grant: AttemptGrant, attempt: Attempt, consumed_at: datetime) -> None:
    grant.status = AttemptGrantStatus.CONSUMED
    grant.pending_slot = None
    grant.consumed_at = consumed_at
    grant.consumed_attempt_id = attempt.id


def _log_attempt_started(session: Session, attempt: Attempt, contest: Contest, source: str) -> None:
    task_config = task_config_of(contest)
    append_event(
        session,
        attempt_id=attempt.id,
        event_type='attempt_started',
        payload={
            'number': attempt.number,
            'started_at': attempt.started_at.isoformat(),
            'deadline_at': attempt.deadline_at.isoformat(),
            'source': source,
            'task_config_snapshot': task_config,
            'task_config_hash': canonical_hash(task_config),
        },
    )


@router.post('/attempts/start', response_model=AttemptStartResponse)
def start_attempt(
    enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> AttemptStartResponse:
    contest = enrollment.contest
    if contest.status != ContestStatus.PUBLISHED:
        raise api_error(status.HTTP_409_CONFLICT, 'CONTEST_NOT_AVAILABLE', 'Контест недоступен.')
    active = active_attempt(session, enrollment.id)
    if active is not None:
        return AttemptStartResponse(attempt=active, created=False)

    previous_number = session.scalar(
        select(func.max(Attempt.number)).where(Attempt.enrollment_id == enrollment.id)
    )
    grant = _required_grant(session, enrollment.id) if previous_number is not None else None
    started_at = utc_now()
    number = (previous_number or 0) + 1
    attempt = Attempt(
        enrollment_id=enrollment.id,
        number=number,
        seed=attempt_seed(contest, number),
        status=AttemptStatus.ACTIVE,
        active_slot=True,
        started_at=started_at,
        deadline_at=started_at + timedelta(minutes=contest.duration_minutes),
    )
    session.add(attempt)
    try:
        session.flush()
        if grant is not None:
            _consume_grant(grant, attempt, started_at)
        _log_attempt_started(
            session, attempt, contest, 'organizer_grant' if grant is not None else 'initial_attempt'
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        active = active_attempt(session, enrollment.id)
        if active is None:
            raise
        return AttemptStartResponse(attempt=active, created=False)
    session.refresh(attempt)
    return AttemptStartResponse(attempt=attempt, created=True)


@router.get('/tasks/current', response_model=CurrentTaskResponse)
def current_task(
    enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> CurrentTaskResponse:
    attempt = require_active_attempt(session, enrollment)
    task, _created = create_or_get_current_task(session, attempt, enrollment.contest)
    return CurrentTaskResponse(task=task)


@router.get('/tasks/progress', response_model=TaskProgressResponse)
def task_progress(
    enrollment: ParticipantEnrollmentDependency, session: SessionDependency
) -> TaskProgressResponse:
    attempt = require_active_attempt(session, enrollment)
    tasks = session.scalars(
        select(TaskInstance).where(TaskInstance.attempt_id == attempt.id).order_by(TaskInstance.ordinal)
    )
    return TaskProgressResponse(
        items=[TaskProgressItem(ordinal=task.ordinal, status=task.status) for task in tasks]
    )


@router.post('/tasks/next', response_model=NextTaskResponse)
def next_task(enrollment: ParticipantEnrollmentDependency, session: SessionDependency) -> NextTaskResponse:
    attempt = require_active_attempt(session, enrollment)
    task, created = create_or_get_current_task(session, attempt, enrollment.contest)
    return NextTaskResponse(task=task, created=created)
