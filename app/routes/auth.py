from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.security import make_signed_token, secure_compare
from app.deps import ADMIN_COOKIE, cookie_secure

router = APIRouter()


@router.post("/admin/login")
def admin_login(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    next_url: Annotated[str, Form(alias="next")] = "/admin",
) -> RedirectResponse:
    settings = get_settings()
    if not secure_compare(username, settings.admin_username) or not secure_compare(password, settings.admin_password):
        return RedirectResponse("/admin/login?error=1", status_code=303)
    response = RedirectResponse(next_url if next_url.startswith("/admin") else "/admin", status_code=303)
    response.set_cookie(
        ADMIN_COOKIE,
        make_signed_token({"role": "admin"}, "admin", settings.admin_session_ttl_seconds),
        max_age=settings.admin_session_ttl_seconds,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(request),
        path="/",
    )
    return response


@router.post("/admin/logout")
def admin_logout() -> RedirectResponse:
    response = RedirectResponse("/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE, path="/")
    return response
