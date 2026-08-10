"""Auth primitives: password hashing + signed session cookies + require_user dependency.

Design choices:
- Password hashing: prefer **bcrypt**, fall back to stdlib scrypt. If bcrypt is installed
  use it, otherwise scrypt (part of hashlib) works without installation. Stored values use a
  self-describing prefix scheme (``bcrypt$...`` / ``scrypt$...``); validation dispatches by
  prefix, so resetting passwords later can upgrade to bcrypt smoothly.
- Sessions: HttpOnly signed cookies (HMAC-SHA256), never stored in localStorage to avoid
  XSS theft; this also reuses existing CORS allow_credentials. The secret comes from the
  environment variable ``QUANT_AUTH_SECRET``; if missing, fall back to a per-process random
  key (prints a warning, invalidated on restart - fail-safe, not a security dependency).

Environment variables:
    QUANT_AUTH_SECRET         Session signing secret (required in production; otherwise
                              all sessions are invalidated on restart).
    QUANT_AUTH_TTL_SECONDS    Session lifetime in seconds, default 7 days.
    QUANT_AUTH_COOKIE_SECURE  Set to 1/true to add Secure to the cookie (HTTPS only).
                              Off by default (local http).
"""

import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
import time

from fastapi import HTTPException, Request, Response

COOKIE_NAME = "quant_session"
_DEFAULT_TTL = 7 * 24 * 60 * 60

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

try:  # bcrypt is optional; fall back to scrypt when missing
    import bcrypt as _bcrypt  # type: ignore[import-not-found]
except Exception:  # noqa: BLE001
    _bcrypt = None


def hash_password(password: str) -> str:
    """Return a self-describing hash string with a scheme prefix."""
    if _bcrypt is not None:
        # bcrypt only uses the first 72 bytes; truncate explicitly for predictable behavior
        raw = password.encode("utf-8")[:72]
        digest = _bcrypt.hashpw(raw, _bcrypt.gensalt()).decode("ascii")
        return f"bcrypt${digest}"
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Dispatch by prefix; any exception is treated as a mismatch (fail-closed)."""
    try:
        if stored.startswith("bcrypt$"):
            if _bcrypt is None:
                return False
            raw = password.encode("utf-8")[:72]
            return _bcrypt.checkpw(raw, stored[len("bcrypt$"):].encode("ascii"))
        if stored.startswith("scrypt$"):
            _, salt_hex, dk_hex = stored.split("$", 2)
            dk = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(salt_hex),
                n=2**14, r=8, p=1, dklen=len(dk_hex) // 2,
            )
            return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:  # noqa: BLE001 — treat any parse/encode error as a validation failure
        return False
    return False


# ---------------------------------------------------------------------------
# Session cookies (HMAC-signed)
# ---------------------------------------------------------------------------

_EPHEMERAL_WARNED = False


def _secret() -> bytes:
    global _EPHEMERAL_WARNED
    value = os.environ.get("QUANT_AUTH_SECRET")
    if value:
        return value.encode("utf-8")
    if not _EPHEMERAL_WARNED:
        print(
            "[auth] warning: QUANT_AUTH_SECRET not set, using an in-process temporary key; "
            "all sessions will be invalidated on restart. Set it in production.",
            file=sys.stderr,
        )
        _EPHEMERAL_WARNED = True
    return _ephemeral_secret()


_EPHEMERAL_SECRET_CACHE = secrets.token_bytes(32)


def _ephemeral_secret() -> bytes:
    return _EPHEMERAL_SECRET_CACHE


def _ttl() -> int:
    try:
        return int(os.environ.get("QUANT_AUTH_TTL_SECONDS", _DEFAULT_TTL))
    except ValueError:
        return _DEFAULT_TTL


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def create_session_token(user_id: int, username: str) -> str:
    payload = {"uid": user_id, "uname": username, "exp": int(time.time()) + _ttl()}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    sig = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
    return f"{body}.{_b64e(sig)}"


def verify_session_token(token: str | None) -> dict | None:
    """Verify signature and expiry; return payload on success, otherwise None."""
    if not token or "." not in token:
        return None
    body, _, sig_part = token.partition(".")
    try:
        expected = hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64d(sig_part)):
            return None
        payload = json.loads(_b64d(body))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload


def _cookie_secure() -> bool:
    return os.environ.get("QUANT_AUTH_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes"}


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=_ttl(),
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(key=COOKIE_NAME, path="/")


def require_user(request: Request) -> dict:
    """FastAPI dependency: validate the session cookie and return the current user;
    raise 401 if missing/expired."""
    payload = verify_session_token(request.cookies.get(COOKIE_NAME))
    if payload is None:
        raise HTTPException(status_code=401, detail="Not authenticated or session expired")
    return {"userId": payload["uid"], "username": payload["uname"]}
