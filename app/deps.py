from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import read_signed_token
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]

ADMIN_COOKIE = "admin_session"


def is_admin(admin_session: str | None = Cookie(default=None)) -> bool:
    payload = read_signed_token(admin_session, "admin")
    return bool(payload and payload.get("role") == "admin")


def require_admin(admin: Annotated[bool, Depends(is_admin)]) -> None:
    if not admin:
        raise HTTPException(status_code=303, headers={"Location": "/admin/login"})


def cookie_secure(request: Request) -> bool:
    return request.url.scheme == "https" or get_settings().public_base_url.startswith("https://")
