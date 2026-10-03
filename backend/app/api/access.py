import hmac

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ..access_codes import expire_code_if_needed
from ..dependencies import SessionDependency, SettingsDependency, api_error
from ..models import AccessCode, AccessCodeStatus, ContestStatus, Enrollment, utc_now
from ..schemas import AccessRedeemRequest, AccessRedeemResponse
from ..security import hash_access_code, issue_bearer_token, normalize_code

router = APIRouter()


def _invalid_code():
    return api_error(status.HTTP_401_UNAUTHORIZED, 'INVALID_ACCESS_CODE', 'Код не найден, отозван или истёк.')


@router.post('/access/redeem', response_model=AccessRedeemResponse)
def redeem_access(
    payload: AccessRedeemRequest, session: SessionDependency, settings: SettingsDependency
) -> AccessRedeemResponse:
    code = normalize_code(payload.code)
    if hmac.compare_digest(code, normalize_code(settings.organizer_code)):
        token, expires_at = issue_bearer_token(settings=settings, role='organizer', subject='organizer')
        return AccessRedeemResponse(access_token=token, role='organizer', expires_at=expires_at)

    access_code = session.scalar(
        select(AccessCode)
        .options(
            joinedload(AccessCode.enrollment).joinedload(Enrollment.contest),
            joinedload(AccessCode.enrollment).joinedload(Enrollment.participant),
        )
        .where(AccessCode.lookup_hash == hash_access_code(code, settings))
    )
    if access_code is None or access_code.status != AccessCodeStatus.ACTIVE:
        raise _invalid_code()
    now = utc_now()
    if expire_code_if_needed(access_code, now):
        session.commit()
        raise _invalid_code()

    enrollment = access_code.enrollment
    if enrollment.contest.status != ContestStatus.PUBLISHED:
        raise api_error(status.HTTP_403_FORBIDDEN, 'CONTEST_NOT_PUBLISHED', 'Контест ещё не опубликован.')
    if access_code.redeemed_at is None:
        access_code.redeemed_at = now
        session.commit()

    token, expires_at = issue_bearer_token(
        settings=settings,
        role='participant',
        subject=enrollment.participant_id,
        additional_claims={
            'enrollment_id': enrollment.id,
            'contest_id': enrollment.contest_id,
            'access_code_id': access_code.id,
        },
        not_after=access_code.expires_at,
    )
    return AccessRedeemResponse(access_token=token, role='participant', expires_at=expires_at)
