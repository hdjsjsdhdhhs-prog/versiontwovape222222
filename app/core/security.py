import base64
import hashlib
import hmac
import json
import time
from typing import Any

from app.core.config import get_settings


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _sign(payload: str, purpose: str) -> str:
    key = f"{purpose}:{get_settings().app_secret_key}".encode("utf-8")
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_signed_token(data: dict[str, Any], purpose: str, ttl_seconds: int | None = None) -> str:
    payload = dict(data)
    if ttl_seconds is not None:
        payload["exp"] = int(time.time()) + ttl_seconds
    raw = _b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    return f"{raw}.{_sign(raw, purpose)}"


def read_signed_token(token: str | None, purpose: str) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(raw, purpose)):
        return None
    try:
        payload = json.loads(_b64decode(raw))
    except (ValueError, json.JSONDecodeError):
        return None
    exp = payload.get("exp")
    if isinstance(exp, int) and exp < int(time.time()):
        return None
    return payload if isinstance(payload, dict) else None


def secure_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))
