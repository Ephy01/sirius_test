from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from .config import Settings
from .models import AccessCode, AccessCodeStatus, Enrollment, EnrollmentStatus
from .security import InvalidTokenError, decode_bearer_token

bearer_scheme = HTTPBearer(auto_error=False)


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


def get_settings_from_app(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request):
    yield from request.app.state.database.session()


SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings_from_app)]
CredentialsDependency = Annotated[
    HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
]


def get_token_claims(
    credentials: CredentialsDependency,
    settings: SettingsDependency,
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "AUTHENTICATION_REQUIRED",
            "Необходим Bearer-токен.",
        )
    try:
        return decode_bearer_token(credentials.credentials, settings)
    except InvalidTokenError as error:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_TOKEN",
            "Токен недействителен или истёк.",
        ) from error


TokenClaimsDependency = Annotated[dict[str, Any], Depends(get_token_claims)]


def require_organizer(claims: TokenClaimsDependency) -> dict[str, Any]:
    if claims.get("role") != "organizer":
        raise api_error(status.HTTP_403_FORBIDDEN, "ORGANIZER_REQUIRED", "Недостаточно прав.")
    return claims


OrganizerDependency = Annotated[dict[str, Any], Depends(require_organizer)]


def require_participant_enrollment(
    claims: TokenClaimsDependency,
    session: SessionDependency,
) -> Enrollment:
    if claims.get("role") != "participant":
        raise api_error(status.HTTP_403_FORBIDDEN, "PARTICIPANT_REQUIRED", "Недостаточно прав.")

    enrollment_id = claims.get("enrollment_id")
    code_id = claims.get("access_code_id")
    if not isinstance(enrollment_id, str) or not isinstance(code_id, str):
        raise api_error(status.HTTP_401_UNAUTHORIZED, "INVALID_TOKEN", "Токен повреждён.")

    access_code = session.scalar(
        select(AccessCode).where(
            AccessCode.id == code_id,
            AccessCode.enrollment_id == enrollment_id,
        )
    )
    if access_code is None or access_code.status != AccessCodeStatus.ACTIVE:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "ACCESS_REVOKED",
            "Код доступа был отозван.",
        )

    enrollment = session.scalar(
        select(Enrollment)
        .options(joinedload(Enrollment.contest), joinedload(Enrollment.participant))
        .where(Enrollment.id == enrollment_id)
    )
    if enrollment is None or enrollment.status != EnrollmentStatus.REGISTERED:
        raise api_error(
            status.HTTP_403_FORBIDDEN,
            "ENROLLMENT_DISABLED",
            "Регистрация участника недоступна.",
        )
    return enrollment


ParticipantEnrollmentDependency = Annotated[
    Enrollment, Depends(require_participant_enrollment)
]

