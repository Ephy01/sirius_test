"""Personal access codes of participants."""

from __future__ import annotations

import hmac
from datetime import datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import Settings
from .dependencies import api_error
from .models import AccessCode, AccessCodeStatus, as_utc, uuid_string
from .security import derive_access_code, hash_access_code

CODE_GENERATION_ATTEMPTS = 12


def expire_code_if_needed(code: AccessCode, now: datetime) -> bool:
    if code.status != AccessCodeStatus.ACTIVE or code.expires_at is None:
        return False
    if as_utc(code.expires_at) > now:
        return False
    code.status = AccessCodeStatus.EXPIRED
    code.active_slot = None
    return True


def new_code_values(session: Session, settings: Settings) -> tuple[str, str, str]:
    for _ in range(CODE_GENERATION_ATTEMPTS):
        code_id = uuid_string()
        plaintext = derive_access_code(code_id, settings)
        lookup_hash = hash_access_code(plaintext, settings)
        if session.scalar(select(AccessCode.id).where(AccessCode.lookup_hash == lookup_hash)) is None:
            return code_id, plaintext, lookup_hash
    raise api_error(
        status.HTTP_503_SERVICE_UNAVAILABLE, 'CODE_GENERATION_FAILED', 'Не удалось создать уникальный код.'
    )


def recover_plaintext(code: AccessCode, settings: Settings) -> str | None:
    plaintext = derive_access_code(code.id, settings)
    if not hmac.compare_digest(hash_access_code(plaintext, settings), code.lookup_hash):
        return None
    return plaintext


def latest_code(codes: list[AccessCode]) -> AccessCode | None:
    return max(codes, key=lambda code: (code.created_at, code.id)) if codes else None


def revoke(code: AccessCode, now: datetime) -> None:
    code.status = AccessCodeStatus.REVOKED
    code.active_slot = None
    code.revoked_at = now
