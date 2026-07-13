"""登录/登出：校验共享口令，签发/清除 cookie。"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.config import settings
from app.core.security import issue_session_token, verify_passphrase

router = APIRouter()


@router.post("/login")
async def login(request: Request, passphrase: str = Form(...)):
    if not verify_passphrase(passphrase):
        return RedirectResponse(url="/login?error=1", status_code=303)

    resp = RedirectResponse(url="/", status_code=303)
    resp.set_cookie(
        key=settings.session_cookie_name,
        value=issue_session_token(),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(settings.session_cookie_name)
    return resp
