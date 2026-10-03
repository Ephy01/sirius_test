from urllib.parse import quote

from fastapi import APIRouter, Body, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from ..access_codes import expire_code_if_needed, latest_code, new_code_values, recover_plaintext, revoke
from ..ai import ProviderError, generate_telemetry_markdown
from ..attempts import active_attempt, expire_stale_attempts, pending_grant
from ..dependencies import (
    AiProviderDependency,
    OrganizerDependency,
    SessionDependency,
    SettingsDependency,
    api_error,
)
from ..models import (
    AccessCode,
    AccessCodeStatus,
    Attempt,
    AttemptGrant,
    AttemptGrantStatus,
    Contest,
    ContestStatus,
    Enrollment,
    Participant,
    utc_now,
)
from ..schemas import (
    AccessCodeSummary,
    AttemptGrantResponse,
    CodeGenerationRequest,
    CodeGenerationResponse,
    CodeRotationRequest,
    EnrollmentBulkCreate,
    EnrollmentBulkResponse,
    GeneratedCodeResponse,
    OrganizerAttemptSummary,
    OrganizerEnrollmentListResponse,
    OrganizerEnrollmentResponse,
)
from ..telemetry import format_enrollment_telemetry
from .contests import get_contest_or_404

router = APIRouter(prefix='/contests/{contest_id}')

NO_STORE = 'private, no-store'


def _get_enrollment_or_404(session: Session, contest_id: str, enrollment_id: str) -> Enrollment:
    enrollment = session.scalar(
        select(Enrollment)
        .options(joinedload(Enrollment.participant))
        .where(Enrollment.id == enrollment_id, Enrollment.contest_id == contest_id)
    )
    if enrollment is None:
        raise api_error(
            status.HTTP_404_NOT_FOUND, 'ENROLLMENT_NOT_FOUND', 'Участник не найден в этом контесте.'
        )
    return enrollment


def _enrollments_with_codes(session: Session, contest_id: str) -> list[Enrollment]:
    return list(
        session.scalars(
            select(Enrollment)
            .options(joinedload(Enrollment.participant), joinedload(Enrollment.access_codes))
            .where(Enrollment.contest_id == contest_id)
            .order_by(Enrollment.created_at)
        )
        .unique()
        .all()
    )


def _code_response(enrollment: Enrollment, code: AccessCode, plaintext: str) -> GeneratedCodeResponse:
    return GeneratedCodeResponse(
        enrollment_id=enrollment.id,
        participant=enrollment.participant,
        code=plaintext,
        last4=code.last4,
        status=code.status,
        expires_at=code.expires_at,
    )


def _issue_code(session: Session, settings, enrollment: Enrollment, expires_at) -> tuple[AccessCode, str]:
    code_id, plaintext, lookup_hash = new_code_values(session, settings)
    code = AccessCode(
        id=code_id,
        enrollment_id=enrollment.id,
        lookup_hash=lookup_hash,
        last4=plaintext[-4:],
        active_slot=True,
        expires_at=expires_at,
    )
    session.add(code)
    return code, plaintext


@router.post('/enrollments', response_model=EnrollmentBulkResponse, status_code=status.HTTP_201_CREATED)
def create_enrollments(
    contest_id: str,
    payload: EnrollmentBulkCreate,
    session: SessionDependency,
    _organizer: OrganizerDependency,
) -> EnrollmentBulkResponse:
    contest = get_contest_or_404(session, contest_id)
    if contest.status != ContestStatus.DRAFT:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'CONTEST_ALREADY_PUBLISHED',
            'Нельзя менять список участников опубликованного контеста.',
        )
    items: list[Enrollment] = []
    created_count = 0
    for item in payload.participants:
        participant = session.scalar(select(Participant).where(Participant.external_ref == item.external_ref))
        if participant is None:
            participant = Participant(external_ref=item.external_ref, display_name=item.display_name)
            session.add(participant)
            session.flush()
        elif participant.display_name != item.display_name:
            participant.display_name = item.display_name

        enrollment = session.scalar(
            select(Enrollment)
            .options(joinedload(Enrollment.participant))
            .where(Enrollment.contest_id == contest.id, Enrollment.participant_id == participant.id)
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


@router.get('/enrollments', response_model=OrganizerEnrollmentListResponse)
def list_enrollments(
    contest_id: str, session: SessionDependency, _organizer: OrganizerDependency
) -> OrganizerEnrollmentListResponse:
    get_contest_or_404(session, contest_id)
    enrollments = list(
        session.scalars(
            select(Enrollment)
            .options(
                joinedload(Enrollment.participant),
                selectinload(Enrollment.access_codes),
                selectinload(Enrollment.attempts),
                selectinload(Enrollment.attempt_grants),
            )
            .where(Enrollment.contest_id == contest_id)
            .order_by(Enrollment.created_at, Enrollment.id)
        )
        .unique()
        .all()
    )
    now = utc_now()
    codes = [code for enrollment in enrollments for code in enrollment.access_codes]
    if any([expire_code_if_needed(code, now) for code in codes]):
        session.commit()
    expire_stale_attempts(session, [attempt for enrollment in enrollments for attempt in enrollment.attempts])

    items = []
    for enrollment in enrollments:
        code = latest_code(enrollment.access_codes)
        attempt = max(enrollment.attempts, key=lambda item: item.number, default=None)
        items.append(
            OrganizerEnrollmentResponse(
                id=enrollment.id,
                contest_id=enrollment.contest_id,
                participant_id=enrollment.participant_id,
                status=enrollment.status,
                participant=enrollment.participant,
                created_at=enrollment.created_at,
                latest_code=AccessCodeSummary.model_validate(code) if code is not None else None,
                latest_attempt=OrganizerAttemptSummary.model_validate(attempt)
                if attempt is not None
                else None,
                attempt_grant_pending=any(
                    grant.status == AttemptGrantStatus.PENDING for grant in enrollment.attempt_grants
                ),
            )
        )
    return OrganizerEnrollmentListResponse(items=items)


def _enrollment_telemetry(session: Session, contest: Contest, enrollment: Enrollment) -> str:
    by_number = (
        select(Attempt).where(Attempt.enrollment_id == enrollment.id).order_by(Attempt.number, Attempt.id)
    )
    expire_stale_attempts(session, list(session.scalars(by_number).all()))
    attempts = session.scalars(
        by_number.options(selectinload(Attempt.tasks), selectinload(Attempt.events))
    ).all()
    return format_enrollment_telemetry(contest=contest, enrollment=enrollment, attempts=list(attempts))


def _attachment(
    content: str, media_type: str, enrollment: Enrollment, prefix: str, extension: str
) -> Response:
    """File download named after the participant, with an ASCII fallback name."""

    label = ''.join(
        character
        for character in enrollment.participant.external_ref.strip()[:32]
        if character not in {'/', '\\'} and ord(character) >= 32
    ).strip()
    filename = f'{prefix}-{enrollment.contest_id}-{enrollment.id}.{extension}'
    preferred = f'{prefix}-{label}-{enrollment.id}.{extension}' if label else filename
    return Response(
        content=content,
        media_type=media_type,
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"; '
            f"filename*=UTF-8''{quote(preferred, safe='')}",
            'Cache-Control': NO_STORE,
            'X-Content-Type-Options': 'nosniff',
        },
    )


@router.get('/enrollments/{enrollment_id}/telemetry', response_class=Response)
def download_enrollment_telemetry(
    contest_id: str, enrollment_id: str, session: SessionDependency, _organizer: OrganizerDependency
) -> Response:
    contest = get_contest_or_404(session, contest_id)
    enrollment = _get_enrollment_or_404(session, contest_id, enrollment_id)
    content = _enrollment_telemetry(session, contest, enrollment)
    return _attachment(content, 'text/plain; charset=utf-8', enrollment, 'sirius-telemetry', 'txt')


@router.get('/enrollments/{enrollment_id}/telemetry/summary', response_class=Response)
def download_enrollment_telemetry_summary(
    contest_id: str,
    enrollment_id: str,
    session: SessionDependency,
    _organizer: OrganizerDependency,
    settings: SettingsDependency,
    ai_provider: AiProviderDependency,
) -> Response:
    if ai_provider is None or not settings.ai_enabled:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            'AI_NOT_CONFIGURED',
            'AI-анализ журналов не настроен на сервере.',
        )
    contest = get_contest_or_404(session, contest_id)
    enrollment = _get_enrollment_or_404(session, contest_id, enrollment_id)
    participant = enrollment.participant
    try:
        content = generate_telemetry_markdown(
            settings=settings,
            provider=ai_provider,
            telemetry=_enrollment_telemetry(session, contest, enrollment),
            contest_title=contest.title,
            participant_label=participant.display_name.strip()
            or participant.external_ref.strip()
            or enrollment.id,
        )
    except ProviderError as error:
        timeout = error.code == 'AI_PROVIDER_TIMEOUT'
        raise api_error(
            status.HTTP_504_GATEWAY_TIMEOUT if timeout else status.HTTP_503_SERVICE_UNAVAILABLE,
            error.code,
            'Не удалось подготовить AI-саммари. Повторите попытку позже.',
        ) from error
    return _attachment(content, 'text/markdown; charset=utf-8', enrollment, 'sirius-summary', 'md')


@router.post('/codes/recover', response_model=CodeGenerationResponse)
def recover_codes(
    contest_id: str,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    _organizer: OrganizerDependency,
) -> CodeGenerationResponse:
    response.headers['Cache-Control'] = NO_STORE
    get_contest_or_404(session, contest_id)
    now = utc_now()
    recovered: list[GeneratedCodeResponse] = []
    unavailable_count = 0
    status_changed = False
    for enrollment in _enrollments_with_codes(session, contest_id):
        for code in enrollment.access_codes:
            status_changed = expire_code_if_needed(code, now) or status_changed
        code = latest_code(
            [code for code in enrollment.access_codes if code.status == AccessCodeStatus.ACTIVE]
        )
        plaintext = recover_plaintext(code, settings) if code is not None else None
        if code is None or plaintext is None:
            unavailable_count += 1
            continue
        recovered.append(_code_response(enrollment, code, plaintext))
    if status_changed:
        session.commit()
    return CodeGenerationResponse(items=recovered, generated_count=0, skipped_count=unavailable_count)


@router.post('/codes', response_model=CodeGenerationResponse)
def generate_codes(
    contest_id: str,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    _organizer: OrganizerDependency,
    payload: CodeGenerationRequest = Body(default_factory=CodeGenerationRequest),
) -> CodeGenerationResponse:
    response.headers['Cache-Control'] = NO_STORE
    get_contest_or_404(session, contest_id)
    now = utc_now()
    generated: list[GeneratedCodeResponse] = []
    generated_count = 0
    skipped_count = 0
    for enrollment in _enrollments_with_codes(session, contest_id):
        active_codes = [
            code
            for code in enrollment.access_codes
            if code.status == AccessCodeStatus.ACTIVE and not expire_code_if_needed(code, now)
        ]
        if active_codes and not payload.rotate:
            code = latest_code(active_codes)
            plaintext = recover_plaintext(code, settings)
            if plaintext is not None:
                generated.append(_code_response(enrollment, code, plaintext))
            skipped_count += 1
            continue
        for code in active_codes:
            revoke(code, now)
        code, plaintext = _issue_code(session, settings, enrollment, payload.expires_at)
        session.flush()
        generated_count += 1
        generated.append(_code_response(enrollment, code, plaintext))
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise api_error(
            status.HTTP_409_CONFLICT, 'CODE_COLLISION', 'Возникла коллизия кодов; повторите генерацию.'
        ) from error
    return CodeGenerationResponse(
        items=generated, generated_count=generated_count, skipped_count=skipped_count
    )


@router.post('/enrollments/{enrollment_id}/codes/rotate', response_model=GeneratedCodeResponse)
def rotate_enrollment_code(
    contest_id: str,
    enrollment_id: str,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
    _organizer: OrganizerDependency,
    payload: CodeRotationRequest = Body(default_factory=CodeRotationRequest),
) -> GeneratedCodeResponse:
    response.headers['Cache-Control'] = NO_STORE
    get_contest_or_404(session, contest_id)
    enrollment = _get_enrollment_or_404(session, contest_id, enrollment_id)
    now = utc_now()
    active_codes = session.scalars(
        select(AccessCode)
        .where(AccessCode.enrollment_id == enrollment.id, AccessCode.status == AccessCodeStatus.ACTIVE)
        .with_for_update()
    ).all()
    for code in active_codes:
        if not expire_code_if_needed(code, now):
            revoke(code, now)
    code, plaintext = _issue_code(session, settings, enrollment, payload.expires_at)
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise api_error(
            status.HTTP_409_CONFLICT, 'CODE_ROTATION_CONFLICT', 'Не удалось заменить код; повторите операцию.'
        ) from error
    session.refresh(code)
    return _code_response(enrollment, code, plaintext)


@router.post('/enrollments/{enrollment_id}/attempts/grant', response_model=AttemptGrantResponse)
def grant_next_attempt(
    contest_id: str, enrollment_id: str, session: SessionDependency, _organizer: OrganizerDependency
) -> AttemptGrantResponse:
    get_contest_or_404(session, contest_id)
    enrollment = _get_enrollment_or_404(session, contest_id, enrollment_id)
    if active_attempt(session, enrollment.id, lock=True) is not None:
        raise api_error(
            status.HTTP_409_CONFLICT,
            'ATTEMPT_ALREADY_ACTIVE',
            'Нельзя выдать новую попытку, пока текущая ещё активна.',
        )

    def response(grant: AttemptGrant, created: bool) -> AttemptGrantResponse:
        return AttemptGrantResponse(
            enrollment_id=enrollment.id, pending=True, created=created, granted_at=grant.granted_at
        )

    grant = pending_grant(session, enrollment.id, lock=True)
    if grant is not None:
        return response(grant, False)
    grant = AttemptGrant(enrollment_id=enrollment.id, status=AttemptGrantStatus.PENDING, pending_slot=True)
    session.add(grant)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = pending_grant(session, enrollment.id)
        if existing is None:
            raise
        return response(existing, False)
    session.refresh(grant)
    return response(grant, True)
