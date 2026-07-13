"""共享口令认证：口令校验 + 签名 cookie。

第一版不做账号/角色，只有一个团队共享口令（补充计划第 7 节）。
用 itsdangerous 对一个固定标记签名写入 cookie，校验签名与有效期即视为已登录。
"""

import hmac

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

_SESSION_MARKER = "authenticated"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.session_secret, salt="douyin-session")


def verify_passphrase(candidate: str) -> bool:
    """常量时间比较，避免时序侧信道。"""
    return hmac.compare_digest(
        candidate.encode("utf-8"), settings.shared_passphrase.encode("utf-8")
    )


def issue_session_token() -> str:
    return _serializer().dumps(_SESSION_MARKER)


def is_valid_session(token: str | None) -> bool:
    if not token:
        return False
    try:
        value = _serializer().loads(token, max_age=settings.session_max_age_seconds)
    except (BadSignature, SignatureExpired):
        return False
    return value == _SESSION_MARKER
