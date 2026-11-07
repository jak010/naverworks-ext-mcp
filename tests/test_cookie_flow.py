"""로컬 단일 사용자 모드(AUTH_MODE=local)의 쿠키 해석 흐름 테스트: 로컬 쿠키 파일 → get_cookie_header → REST / MCP / 로그인"""

import json
import contextvars

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.core import cookie, client as nw_client
from app.core.auth_context import set_current_user_cookie
from app.main import app

pytestmark = pytest.mark.usefixtures("local_mode")

JAR_COOKIE = "WORKS_SES=jar-session-value-1234567890; WORKS_USER_ID=jar-user"


def write_jar(cookie_str: str = JAR_COOKIE) -> None:
    lines = ["# Netscape HTTP Cookie File"]
    for pair in cookie_str.split("; "):
        name, val = pair.split("=", 1)
        lines.append("\t".join([".worksmobile.com", "TRUE", "/", "TRUE", "2147483647", name, val]))
    with open(config.COOKIE_JAR_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def run_isolated(fn):
    """ContextVar 상태가 다른 테스트로 새지 않도록 새 컨텍스트에서 실행합니다."""
    return contextvars.Context().run(fn)


@pytest.fixture
def upstream(monkeypatch):
    """네이버웍스 업스트림을 MockTransport로 대체하고 수신한 Cookie 헤더를 기록합니다."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("cookie"))
        return httpx.Response(200, json=[{"spaceId": "s-1", "spaceName": "테스트 스페이스"}])

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake_get_async_client():
        return mock_client

    monkeypatch.setattr(nw_client, "get_async_client", fake_get_async_client)
    return seen


# ---------------------------------------------------------------------------
# get_cookie_header 우선순위
# ---------------------------------------------------------------------------

def test_no_cookie_anywhere_returns_empty():
    assert run_isolated(cookie.get_cookie_header) == ""
    assert run_isolated(cookie.is_cookie_valid) is False


def test_local_jar_is_used_as_fallback():
    write_jar()
    assert run_isolated(cookie.get_cookie_header) == JAR_COOKIE
    assert run_isolated(cookie.is_cookie_valid) is True
    assert run_isolated(cookie.describe_cookie_source)["source"] == "local_cookie_jar"


def test_local_jar_ignored_in_multi_user_mode(monkeypatch):
    write_jar()
    monkeypatch.setattr(config, "AUTH_MODE", "multi_user")
    assert run_isolated(cookie.get_cookie_header) == ""


def test_context_cookie_takes_priority_over_jar():
    write_jar()

    def fn():
        set_current_user_cookie("WORKS_SES=from-context-0123456789", source="http_request")
        return cookie.get_cookie_header()

    assert run_isolated(fn) == "WORKS_SES=from-context-0123456789"


def test_env_cookie_takes_priority_over_jar(monkeypatch):
    write_jar()
    monkeypatch.setenv("NAVERWORKS_COOKIE", "WORKS_SES=from-env-0123456789")
    assert run_isolated(cookie.get_cookie_header) == "WORKS_SES=from-env-0123456789"


def test_jar_cache_picks_up_file_changes():
    write_jar()
    assert run_isolated(cookie.get_cookie_header) == JAR_COOKIE
    import os
    write_jar("WORKS_SES=rotated-session-0123456789")
    # mtime 해상도와 무관하게 갱신을 보장하기 위해 mtime을 강제로 변경
    st = os.stat(config.COOKIE_JAR_PATH)
    os.utime(config.COOKIE_JAR_PATH, (st.st_atime, st.st_mtime + 5))
    assert run_isolated(cookie.get_cookie_header) == "WORKS_SES=rotated-session-0123456789"


# ---------------------------------------------------------------------------
# 브라우저 로그인: 쿠키 파일 저장 후 성공으로 인식해야 함
# ---------------------------------------------------------------------------

def test_login_via_browser_succeeds_once_jar_is_written(monkeypatch):
    calls = {"n": 0}

    def fake_refresh():
        calls["n"] += 1
        if calls["n"] >= 2:  # 첫 검사에서는 로그인 안 됨, 폴링 중 로그인 완료
            write_jar()
            return True
        return False

    monkeypatch.setattr(cookie, "refresh_cookie_jar", fake_refresh)
    monkeypatch.setattr(cookie, "open_browser", lambda url="": True)
    monkeypatch.setattr(cookie, "notify_macos", lambda *a, **k: None)
    monkeypatch.setattr(cookie.time, "sleep", lambda s: None)

    res = run_isolated(lambda: cookie.login_via_browser(timeout_seconds=5))
    assert res["success"] is True
    assert res["cookiePath"] == config.COOKIE_JAR_PATH


def test_login_success_is_judged_by_saved_file_not_request_cookie(monkeypatch):
    """로그인 성공 여부는 현재 요청 쿠키가 아니라 방금 저장된 쿠키 파일 기준으로 판단해야 합니다."""
    monkeypatch.setattr(config, "AUTH_MODE", "multi_user")

    def fake_refresh():
        write_jar()
        return True

    monkeypatch.setattr(cookie, "refresh_cookie_jar", fake_refresh)
    res = run_isolated(lambda: cookie.login_via_browser(timeout_seconds=5))
    assert res["success"] is True


# ---------------------------------------------------------------------------
# REST /api/v1 라우트
# ---------------------------------------------------------------------------

def test_rest_route_without_cookie_returns_401(upstream):
    with TestClient(app) as c:
        r = c.get("/api/v1/spaces")
    assert r.status_code == 401
    assert upstream == []


def test_rest_route_uses_local_jar(upstream):
    write_jar()
    with TestClient(app) as c:
        r = c.get("/api/v1/spaces")
    assert r.status_code == 200
    assert upstream == [JAR_COOKIE]


def test_rest_route_uses_request_header_cookie(upstream):
    write_jar()
    with TestClient(app) as c:
        r = c.get("/api/v1/spaces", headers={"X-Naverworks-Cookie": "WORKS_SES=header-cookie-0123456789"})
    assert r.status_code == 200
    assert upstream == ["WORKS_SES=header-cookie-0123456789"]


def test_rest_request_cookie_does_not_leak_to_next_request(upstream):
    write_jar()
    with TestClient(app) as c:
        c.get("/api/v1/spaces", headers={"X-Naverworks-Cookie": "WORKS_SES=header-cookie-0123456789"})
        c.get("/api/v1/spaces")
    assert upstream == ["WORKS_SES=header-cookie-0123456789", JAR_COOKIE]


# ---------------------------------------------------------------------------
# MCP 도구
# ---------------------------------------------------------------------------

def test_mcp_tool_uses_local_jar(upstream):
    write_jar()
    with TestClient(app) as c:
        r = c.post("/mcp/call", json={"name": "list_spaces", "arguments": {}})
    body = r.json()
    assert body["isError"] is False
    assert upstream == [JAR_COOKIE]


def test_mcp_auth_status_reports_local_jar():
    write_jar()
    with TestClient(app) as c:
        r = c.post("/mcp/call", json={"name": "get_auth_status", "arguments": {}})
    status = json.loads(r.json()["content"][0]["text"])
    assert status["isAuthenticated"] is True
    assert status["cookieSource"] == "local_cookie_jar"
    assert status["cookiePath"] == config.COOKIE_JAR_PATH
