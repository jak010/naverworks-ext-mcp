"""
MCP User Authentication Context (Multi-Tenant & Per-User Isolation)
각 MCP 사용자/세션별로 쿠키 정보 및 인증 컨텍스트를 독립적으로 격리하고 바인딩합니다.
"""

from contextvars import ContextVar
from typing import Optional

_current_user_cookie: ContextVar[Optional[str]] = ContextVar("current_user_cookie", default=None)
_current_cookie_source: ContextVar[str] = ContextVar("current_cookie_source", default="default")
_current_cookie_path: ContextVar[Optional[str]] = ContextVar("current_cookie_path", default=None)
_current_user_id: ContextVar[Optional[str]] = ContextVar("current_user_id", default=None)


def set_current_user_cookie(
    cookie: Optional[str],
    source: str = "override",
    cookie_path: Optional[str] = None,
    user_id: Optional[str] = None
) -> None:
    """현재 비동기 요청/세션의 사용자 쿠키 정보를 ContextVar에 안전하게 바인딩합니다."""
    _current_user_cookie.set(cookie)
    _current_cookie_source.set(source)
    if cookie_path:
        _current_cookie_path.set(cookie_path)
    if user_id:
        _current_user_id.set(user_id)


def get_current_user_cookie() -> Optional[str]:
    """현재 요청/세션 컨텍스트에 바인딩된 MCP 사용자의 쿠키를 반환합니다."""
    return _current_user_cookie.get()


def get_current_cookie_source() -> str:
    """현재 쿠키의 출처 ('session_header', 'session_path', 'tool_input', 'default')를 반환합니다."""
    return _current_cookie_source.get()


def get_current_cookie_path() -> Optional[str]:
    """현재 쿠키 파일 경로(있는 경우)를 반환합니다."""
    return _current_cookie_path.get()


def clear_current_user_cookie() -> None:
    """현재 컨텍스트의 사용자 인증 정보를 초기화합니다."""
    _current_user_cookie.set(None)
    _current_cookie_source.set("default")
    _current_cookie_path.set(None)
    _current_user_id.set(None)

