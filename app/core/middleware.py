"""认证中间件：未登录跳转 /login。

放行：/login、/logout、静态资源、健康检查。其余页面/接口要求有效会话 cookie。
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse

from app.config import settings
from app.core.security import is_valid_session

# 无需登录即可访问的路径前缀
_PUBLIC_PREFIXES = ("/login", "/logout", "/static", "/health", "/favicon")


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in _PUBLIC_PREFIXES)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if _is_public(path):
            return await call_next(request)

        token = request.cookies.get(settings.session_cookie_name)
        if is_valid_session(token):
            return await call_next(request)

        # API 请求返回 401，页面请求跳登录
        if path.startswith("/api/"):
            return JSONResponse({"detail": "未登录"}, status_code=401)
        return RedirectResponse(url="/login", status_code=303)
