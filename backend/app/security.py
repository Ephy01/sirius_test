import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from .config import Settings

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


class InvalidTokenError(ValueError):
    pass


def normalize_code(code: str) -> str:
    return code.strip().upper()


def hash_access_code(code: str, settings: Settings) -> str:
    return hmac.new(
        settings.code_hmac_secret.encode("utf-8"),
        normalize_code(code).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_access_code() -> str:
    first = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    second = "".join(secrets.choice(CODE_ALPHABET) for _ in range(4))
    return f"SG-{first}-{second}"


def derive_access_code(code_id: str, settings: Settings) -> str:
    digest = hmac.new(
        settings.code_hmac_secret.encode("utf-8"),
        b"sirius-gate/access-code/v1\0" + code_id.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    value = int.from_bytes(digest, "big")
    symbols: list[str] = []
    for _ in range(8):
        value, index = divmod(value, len(CODE_ALPHABET))
        symbols.append(CODE_ALPHABET[index])
    plaintext = "".join(symbols)
    return f"SG-{plaintext[:4]}-{plaintext[4:]}"


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _base64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as error:
        raise InvalidTokenError("Malformed token encoding") from error


def issue_bearer_token(
    *,
    settings: Settings,
    role: Literal["organizer", "participant"],
    subject: str,
    additional_claims: dict[str, Any] | None = None,
    not_after: datetime | None = None,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.access_token_ttl_minutes)
    if not_after is not None:
        normalized_limit = (
            not_after.replace(tzinfo=timezone.utc)
            if not_after.tzinfo is None
            else not_after.astimezone(timezone.utc)
        )
        expires_at = min(expires_at, normalized_limit)

    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(12),
    }
    if additional_claims:
        payload.update(additional_claims)

    encoded_header = _base64url_encode(
        json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    encoded_payload = _base64url_encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    )
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(
        settings.security_secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    token = f"{encoded_header}.{encoded_payload}.{_base64url_encode(signature)}"
    return token, expires_at


def decode_bearer_token(token: str, settings: Settings) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise InvalidTokenError("Malformed token")

    encoded_header, encoded_payload, encoded_signature = parts
    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    expected_signature = hmac.new(
        settings.security_secret.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    supplied_signature = _base64url_decode(encoded_signature)
    if not hmac.compare_digest(expected_signature, supplied_signature):
        raise InvalidTokenError("Invalid signature")

    try:
        header = json.loads(_base64url_decode(encoded_header))
        payload = json.loads(_base64url_decode(encoded_payload))
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as error:
        raise InvalidTokenError("Malformed token payload") from error

    if header != {"alg": "HS256", "typ": "JWT"}:
        raise InvalidTokenError("Unsupported token header")
    if payload.get("role") not in {"organizer", "participant"}:
        raise InvalidTokenError("Invalid token role")
    if not isinstance(payload.get("sub"), str) or not payload["sub"]:
        raise InvalidTokenError("Invalid token subject")
    if not isinstance(payload.get("exp"), int):
        raise InvalidTokenError("Missing token expiry")
    if payload["exp"] <= int(datetime.now(timezone.utc).timestamp()):
        raise InvalidTokenError("Token expired")
    return payload
