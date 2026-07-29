import hmac
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Body, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from .dependencies import (
    OrganizerDependency,
    ParticipantEnrollmentDependency,
    SessionDependency,
    SettingsDependency,
    api_error,
)
from .environments import (
    CHESS960_FAMILY,
    CHESS960_GENERATOR_VERSION,
    derive_task_seed,
    evaluate_task,
    generate_task,
)
from .models import (
    AccessCode,
    AccessCodeStatus,
    Attempt,
    AttemptEvent,
    AttemptStatus,
    Contest,
    ContestStatus,
    Enrollment,
    Participant,
    TaskInstance,
    TaskStatus,
    utc_now,
)
from .schemas import (
    AccessRedeemRequest,
    AccessRedeemResponse,
    AttemptStartResponse,
    CodeGenerationRequest,
    CodeGenerationResponse,
    ContestCreate,
    ContestListResponse,
    ContestResponse,
    CurrentTaskResponse,
    EnrollmentBulkCreate,
    EnrollmentBulkResponse,
    EnrollmentResponse,
    GeneratedCodeResponse,
    HealthResponse,
    NextTaskResponse,
    ParticipantContextResponse,
    TaskActionResponse,
    TaskAnswerRequest,
)
from .security import (
    generate_access_code,
    hash_access_code,
    issue_bearer_token,
    normalize_code,
)

router = APIRouter(prefix="/api/v1")


def _as_utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _get_contest_or_404(session: SessionDependency, contest_id: str) -> Contest:
    contest = session.get(Contest, contest_id)
    if contest is None:
        raise api_error(status.HTTP_404_NOT_FOUND, "CONTEST_NOT_FOUND", "Контест не найден.")
    return contest


def _expire_access_code_if_needed(code: AccessCode, now: datetime) -> bool:
    if (
        code.status == AccessCodeStatus.ACTIVE
        and code.expires_at is not None
        and _as_utc(code.expires_at) <= now
    ):
        code.status = AccessCodeStatus.EXPIRED
        code.active_slot = None
        return True
    return False


def _active_attempt(
    session: SessionDependency,
    enrollment_id: str,
    *,
    lock: bool = False,
) -> Attempt | None:
    statement = select(Attempt).where(
        Attempt.enrollment_id == enrollment_id,
        Attempt.status == AttemptStatus.ACTIVE,
    )
    if lock:
        statement = statement.with_for_update()
    attempt = session.scalar(statement)
    if attempt is not None and _as_utc(attempt.deadline_at) <= utc_now():
        attempt.status = AttemptStatus.EXPIRED
        attempt.active_slot = None
        attempt.finished_at = utc_now()
        _append_event(
            session,
            attempt_id=attempt.id,
            event_type="attempt_expired",
            payload={"deadline_at": _as_utc(attempt.deadline_at).isoformat()},
        )
        session.commit()
        return None
    return attempt


def _require_active_attempt(
    session: SessionDependency,
    enrollment: Enrollment,
) -> Attempt:
    # PostgreSQL serializes task commands per attempt. SQLite ignores
    # FOR UPDATE but still enforces the uniqueness constraints used below.
    attempt = _active_attempt(session, enrollment.id, lock=True)
    if attempt is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "ACTIVE_ATTEMPT_REQUIRED",
            "Сначала запустите попытку. Истёкшую попытку продолжить нельзя.",
        )
    return attempt


def _active_task(session: SessionDependency, attempt_id: str) -> TaskInstance | None:
    return session.scalar(
        select(TaskInstance).where(
            TaskInstance.attempt_id == attempt_id,
            TaskInstance.status == TaskStatus.ACTIVE,
        )
    )


def _append_event(
    session: SessionDependency,
    *,
    attempt_id: str,
    event_type: str,
    task_instance_id: str | None = None,
    payload: dict | None = None,
) -> AttemptEvent:
    stored_sequence = session.scalar(
        select(func.max(AttemptEvent.sequence)).where(
            AttemptEvent.attempt_id == attempt_id
        )
    )
    pending_sequences = [
        event.sequence
        for event in session.new
        if isinstance(event, AttemptEvent) and event.attempt_id == attempt_id
    ]
    sequence = max([stored_sequence or 0, *pending_sequences]) + 1
    event = AttemptEvent(
        attempt_id=attempt_id,
        task_instance_id=task_instance_id,
        event_type=event_type,
        sequence=sequence,
        payload=payload or {},
    )
    session.add(event)
    return event


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return min(maximum, max(minimum, value))


def _chess960_task_settings(contest: Contest) -> tuple[int, int, int] | None:
    """Read the supported family from both legacy and current contest configs."""

    config = contest.task_config if isinstance(contest.task_config, dict) else {}
    families = config.get("families")
    selected: dict | None = None

    if isinstance(families, list):
        for family in families:
            if isinstance(family, str) and family in {"chess960", "chess_960"}:
                selected = {}
                break
            if not isinstance(family, dict):
                continue
            key = family.get("key")
            if key in {"chess960", "chess_960"} and family.get("enabled", True):
                selected = family
                break
        if selected is None:
            return None
    else:
        # Empty and older contests predate the family constructor; Chess960 is
        # their safe default for this MVP.
        selected = {}

    initial = _bounded_int(
        selected.get("initial_difficulty"),
        default=1,
        minimum=1,
        maximum=10,
    )
    maximum = _bounded_int(
        selected.get("max_difficulty"),
        default=10,
        minimum=initial,
        maximum=10,
    )
    threshold = _bounded_int(
        config.get("adaptation_threshold"),
        default=3,
        minimum=1,
        maximum=20,
    )
    return initial, maximum, threshold


def _task_difficulty(
    session: SessionDependency,
    *,
    attempt_id: str,
    initial: int,
    maximum: int,
    threshold: int,
) -> int:
    answered_tasks = session.scalars(
        select(TaskInstance).where(
            TaskInstance.attempt_id == attempt_id,
            TaskInstance.family == CHESS960_FAMILY,
            TaskInstance.status == TaskStatus.ANSWERED,
        )
    )
    correct_count = sum(
        1
        for task in answered_tasks
        if isinstance(task.evaluation_state, dict)
        and task.evaluation_state.get("correct") is True
    )
    return min(maximum, initial + correct_count // threshold)


def _create_or_get_current_task(
    session: SessionDependency,
    *,
    attempt: Attempt,
    contest: Contest,
) -> tuple[TaskInstance, bool]:
    current = _active_task(session, attempt.id)
    if current is not None:
        return current, False

    settings = _chess960_task_settings(contest)
    if settings is None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TASK_FAMILY_NOT_AVAILABLE",
            "В контесте пока нет семейства задач, поддерживаемого этой версией MVP.",
        )
    initial, maximum, threshold = settings
    latest_ordinal = session.scalar(
        select(func.max(TaskInstance.ordinal)).where(
            TaskInstance.attempt_id == attempt.id
        )
    )
    ordinal = (latest_ordinal or 0) + 1
    difficulty = _task_difficulty(
        session,
        attempt_id=attempt.id,
        initial=initial,
        maximum=maximum,
        threshold=threshold,
    )
    task_seed = derive_task_seed(
        attempt.seed,
        ordinal,
        CHESS960_FAMILY,
        CHESS960_GENERATOR_VERSION,
    )
    generated = generate_task(
        family=CHESS960_FAMILY,
        generator_version=CHESS960_GENERATOR_VERSION,
        seed=task_seed,
        difficulty=difficulty,
    )
    task = TaskInstance(
        attempt_id=attempt.id,
        ordinal=ordinal,
        family=CHESS960_FAMILY,
        generator_version=CHESS960_GENERATOR_VERSION,
        seed=task_seed,
        difficulty=difficulty,
        status=TaskStatus.ACTIVE,
        active_slot=True,
        public_state=generated.public_state,
        private_state=generated.private_state,
    )
    session.add(task)
    try:
        session.flush()
        _append_event(
            session,
            attempt_id=attempt.id,
            task_instance_id=task.id,
            event_type="task_generated",
            payload={
                "ordinal": ordinal,
                "family": task.family,
                "generator_version": task.generator_version,
                "seed": task.seed,
                "difficulty": task.difficulty,
            },
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        current = _active_task(session, attempt.id)
        if current is None:
            raise
        return current, False
    session.refresh(task)
    return task, True


def _get_active_task_or_error(
    session: SessionDependency,
    *,
    attempt: Attempt,
    task_id: str,
) -> TaskInstance:
    task = session.scalar(
        select(TaskInstance).where(
            TaskInstance.id == task_id,
            TaskInstance.attempt_id == attempt.id,
        )
    )
    if task is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND,
            "TASK_NOT_FOUND",
            "Задача не найдена в текущей попытке.",
        )
    if task.status != TaskStatus.ACTIVE:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TASK_ALREADY_CLOSED",
            "Ответ на эту задачу уже зафиксирован.",
        )
    return task


@router.get("/health", response_model=HealthResponse)
def health(settings: SettingsDependency) -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


@router.post("/access/redeem", response_model=AccessRedeemResponse)
def redeem_access(
    payload: AccessRedeemRequest,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AccessRedeemResponse:
    normalized_code = normalize_code(payload.code)

    if hmac.compare_digest(normalized_code, normalize_code(settings.organizer_code)):
        token, expires_at = issue_bearer_token(
            settings=settings,
            role="organizer",
            subject="organizer",
        )
        return AccessRedeemResponse(
            access_token=token,
            role="organizer",
            expires_at=expires_at,
        )

    lookup_hash = hash_access_code(normalized_code, settings)
    access_code = session.scalar(
        select(AccessCode)
        .options(
            joinedload(AccessCode.enrollment).joinedload(Enrollment.contest),
            joinedload(AccessCode.enrollment).joinedload(Enrollment.participant),
        )
        .where(AccessCode.lookup_hash == lookup_hash)
    )
    if access_code is None or access_code.status != AccessCodeStatus.ACTIVE:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_ACCESS_CODE",
            "Код не найден, отозван или истёк.",
        )

    now = utc_now()
    if _expire_access_code_if_needed(access_code, now):
        session.commit()
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_ACCESS_CODE",
            "Код не найден, отозван или истёк.",
        )

    enrollment = access_code.enrollment
    contest = enrollment.contest
    if contest.status != ContestStatus.PUBLISHED:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "CONTEST_NOT_PUBLISHED",
            "Контест ещё не опубликован.",
        )

    if access_code.redeemed_at is None:
        access_code.redeemed_at = now
        session.commit()

    token, expires_at = issue_bearer_token(
        settings=settings,
        role="participant",
        subject=enrollment.participant_id,
        additional_claims={
            "enrollment_id": enrollment.id,
            "contest_id": enrollment.contest_id,
            "access_code_id": access_code.id,
        },
        not_after=access_code.expires_at,
    )
    return AccessRedeemResponse(
        access_token=token,
        role="participant",
        expires_at=expires_at,
    )


@router.get("/contests", response_model=ContestListResponse)
def list_contests(
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> ContestListResponse:
    contests = list(session.scalars(select(Contest).order_by(Contest.created_at.desc())).all())
    return ContestListResponse(items=contests)


@router.post("/contests", response_model=ContestResponse, status_code=status.HTTP_201_CREATED)
def create_contest(
    payload: ContestCreate,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> Contest:
    contest = Contest(**payload.model_dump())
    session.add(contest)
    session.commit()
    session.refresh(contest)
    return contest


@router.post(
    "/contests/{contest_id}/enrollments",
    response_model=EnrollmentBulkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollments(
    contest_id: str,
    payload: EnrollmentBulkCreate,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> EnrollmentBulkResponse:
    contest = _get_contest_or_404(session, contest_id)
    if contest.status != ContestStatus.DRAFT:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CONTEST_ALREADY_PUBLISHED",
            "Нельзя менять список участников опубликованного контеста.",
        )

    items: list[Enrollment] = []
    created_count = 0
    for item in payload.participants:
        participant = session.scalar(
            select(Participant).where(Participant.external_ref == item.external_ref)
        )
        if participant is None:
            participant = Participant(
                external_ref=item.external_ref,
                display_name=item.display_name,
            )
            session.add(participant)
            session.flush()
        elif participant.display_name != item.display_name:
            participant.display_name = item.display_name

        enrollment = session.scalar(
            select(Enrollment)
            .options(joinedload(Enrollment.participant))
            .where(
                Enrollment.contest_id == contest.id,
                Enrollment.participant_id == participant.id,
            )
        )
        if enrollment is None:
            enrollment = Enrollment(contest_id=contest.id, participant_id=participant.id)
            enrollment.participant = participant
            session.add(enrollment)
            session.flush()
            created_count += 1
        items.append(enrollment)

    session.commit()
    return EnrollmentBulkResponse(items=items, created_count=created_count)


@router.post("/contests/{contest_id}/codes", response_model=CodeGenerationResponse)
def generate_codes(
    contest_id: str,
    session: SessionDependency,
    settings: SettingsDependency,
    _organizer: OrganizerDependency,
    payload: CodeGenerationRequest = Body(default_factory=CodeGenerationRequest),
) -> CodeGenerationResponse:
    _get_contest_or_404(session, contest_id)
    enrollments = list(
        session.scalars(
            select(Enrollment)
            .options(joinedload(Enrollment.participant), joinedload(Enrollment.access_codes))
            .where(Enrollment.contest_id == contest_id)
            .order_by(Enrollment.created_at)
        )
        .unique()
        .all()
    )
    now = utc_now()
    generated: list[GeneratedCodeResponse] = []
    skipped_count = 0

    for enrollment in enrollments:
        active_codes = [
            code
            for code in enrollment.access_codes
            if code.status == AccessCodeStatus.ACTIVE
            and not _expire_access_code_if_needed(code, now)
        ]
        if active_codes and not payload.rotate:
            skipped_count += 1
            continue
        if payload.rotate:
            for code in active_codes:
                code.status = AccessCodeStatus.REVOKED
                code.active_slot = None
                code.revoked_at = now

        plaintext: str | None = None
        lookup_hash: str | None = None
        for _ in range(12):
            candidate = generate_access_code()
            candidate_hash = hash_access_code(candidate, settings)
            hash_exists = session.scalar(
                select(AccessCode.id).where(AccessCode.lookup_hash == candidate_hash)
            )
            if hash_exists is not None:
                continue
            plaintext = candidate
            lookup_hash = candidate_hash
            break
        if plaintext is None or lookup_hash is None:
            raise api_error(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "CODE_GENERATION_FAILED",
                "Не удалось создать уникальный код.",
            )

        code = AccessCode(
            enrollment_id=enrollment.id,
            lookup_hash=lookup_hash,
            last4=plaintext[-4:],
            active_slot=True,
            expires_at=payload.expires_at,
        )
        session.add(code)
        session.flush()
        generated.append(
            GeneratedCodeResponse(
                enrollment_id=enrollment.id,
                participant=enrollment.participant,
                code=plaintext,
                last4=code.last4,
                status=code.status,
                expires_at=code.expires_at,
            )
        )

    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CODE_COLLISION",
            "Возникла коллизия кодов; повторите генерацию.",
        ) from error

    return CodeGenerationResponse(
        items=generated,
        generated_count=len(generated),
        skipped_count=skipped_count,
    )


@router.post("/contests/{contest_id}/publish", response_model=ContestResponse)
def publish_contest(
    contest_id: str,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> Contest:
    contest = _get_contest_or_404(session, contest_id)
    if contest.status == ContestStatus.DRAFT:
        contest.status = ContestStatus.PUBLISHED
        contest.published_at = utc_now()
        session.commit()
        session.refresh(contest)
    return contest


@router.get("/participant/context", response_model=ParticipantContextResponse)
def participant_context(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> ParticipantContextResponse:
    attempt = _active_attempt(session, enrollment.id)
    return ParticipantContextResponse(
        contest=enrollment.contest,
        enrollment=EnrollmentResponse.model_validate(enrollment),
        participant=enrollment.participant,
        active_attempt=attempt,
    )


@router.post("/participant/attempts/start", response_model=AttemptStartResponse)
def start_attempt(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> AttemptStartResponse:
    if enrollment.contest.status != ContestStatus.PUBLISHED:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CONTEST_NOT_AVAILABLE",
            "Контест недоступен.",
        )

    active = _active_attempt(session, enrollment.id)
    if active is not None:
        return AttemptStartResponse(attempt=active, created=False)

    previous_count = session.scalar(
        select(func.count(Attempt.id)).where(Attempt.enrollment_id == enrollment.id)
    )
    if previous_count:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "ATTEMPT_NOT_AVAILABLE",
            "Для новой попытки требуется разрешение организатора.",
        )

    started_at = utc_now()
    attempt = Attempt(
        enrollment_id=enrollment.id,
        number=1,
        seed=secrets.randbits(63),
        status=AttemptStatus.ACTIVE,
        active_slot=True,
        started_at=started_at,
        deadline_at=started_at + timedelta(minutes=enrollment.contest.duration_minutes),
    )
    session.add(attempt)
    try:
        session.flush()
        _append_event(
            session,
            attempt_id=attempt.id,
            event_type="attempt_started",
            payload={
                "number": attempt.number,
                "started_at": attempt.started_at.isoformat(),
                "deadline_at": attempt.deadline_at.isoformat(),
            },
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        active = _active_attempt(session, enrollment.id)
        if active is None:
            raise
        return AttemptStartResponse(attempt=active, created=False)
    session.refresh(attempt)
    return AttemptStartResponse(attempt=attempt, created=True)


@router.get("/participant/tasks/current", response_model=CurrentTaskResponse)
def current_task(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> CurrentTaskResponse:
    attempt = _require_active_attempt(session, enrollment)
    task, _created = _create_or_get_current_task(
        session,
        attempt=attempt,
        contest=enrollment.contest,
    )
    return CurrentTaskResponse(task=task)


@router.post("/participant/tasks/next", response_model=NextTaskResponse)
def next_task(
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> NextTaskResponse:
    attempt = _require_active_attempt(session, enrollment)
    task, created = _create_or_get_current_task(
        session,
        attempt=attempt,
        contest=enrollment.contest,
    )
    return NextTaskResponse(task=task, created=created)


@router.post(
    "/participant/tasks/{task_id}/answer",
    response_model=TaskActionResponse,
)
def answer_task(
    task_id: str,
    payload: TaskAnswerRequest,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> TaskActionResponse:
    attempt = _require_active_attempt(session, enrollment)
    task = _get_active_task_or_error(session, attempt=attempt, task_id=task_id)
    evaluation = evaluate_task(
        family=task.family,
        generator_version=task.generator_version,
        answer=payload.answer,
        private_state=task.private_state,
    )
    completed_at = utc_now()
    task.participant_answer = payload.answer
    task.evaluation_state = evaluation
    task.status = TaskStatus.ANSWERED
    task.active_slot = None
    task.completed_at = completed_at
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="answer_submitted",
        payload={"answer": payload.answer},
    )
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="answer_evaluated",
        payload=evaluation,
    )
    session.commit()
    session.refresh(task)
    return TaskActionResponse(
        task=task,
        message="Ответ зафиксирован. Можно перейти к следующей задаче.",
    )


@router.post(
    "/participant/tasks/{task_id}/skip",
    response_model=TaskActionResponse,
)
def skip_task(
    task_id: str,
    enrollment: ParticipantEnrollmentDependency,
    session: SessionDependency,
) -> TaskActionResponse:
    attempt = _require_active_attempt(session, enrollment)
    task = _get_active_task_or_error(session, attempt=attempt, task_id=task_id)
    task.status = TaskStatus.SKIPPED
    task.active_slot = None
    task.completed_at = utc_now()
    _append_event(
        session,
        attempt_id=attempt.id,
        task_instance_id=task.id,
        event_type="task_skipped",
    )
    session.commit()
    session.refresh(task)
    return TaskActionResponse(
        task=task,
        message="Задача пропущена. Можно перейти к следующей.",
    )
