"""익명 다중 사용자 서비스 모델 검증 (AUTH_MODE=multi_user, HTTP 서버 기본값)

요구사항
  R1. 각 사용자는 자신의 쿠키를 직접 제공해야 하며, 제공하지 않으면 어떤 데이터 도구도 실행되지 않는다.
      (서버 호스트의 쿠키 파일 / 환경 변수 쿠키를 절대 대신 사용하지 않는다.)
  R2. 업스트림(네이버웍스)으로 나가는 모든 요청에는 그 요청을 보낸 사용자의 쿠키만 실린다.
  R3. 동시에 여러 사용자가 요청해도 쿠키/응답이 섞이지 않는다. (ContextVar, SSE 세션, 캐시)
  R4. 익명 사용자가 서버 호스트의 자격 증명(로컬 쿠키 파일, Chrome 키체인, 브라우저 로그인)을 빌려 쓸 수 없다.
  R5. 사용자가 전달한 쿠키가 서버 접근 로그에 평문으로 남지 않는다.
"""

import json
import asyncio
import logging
import os
import subprocess
import sys

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.config import DEFAULT_DOMAIN_ID as D, DEFAULT_INSTANCE_CODE as I
from app.core import cookie
from app.main import app
from app.api.mcp import session_manager, MCPSession
from tests.conftest import write_netscape_cookie_file

USER_A = "WORKS_SES=aaaa-session-0000000001; WORKS_USER_ID=user-a"
USER_B = "WORKS_SES=bbbb-session-0000000002; WORKS_USER_ID=user-b"
SERVER_OWNER = "WORKS_SES=server-owner-secret-999; WORKS_USER_ID=owner"

DATA_TOOLS = [
    # (tool, arguments, upstream method, upstream path)
    ("list_spaces", {}, "GET", f"/rd/{D}/api/v1/spaces"),
    ("get_space", {"spaceId": "s-1"}, "GET", f"/rd/{D}/api/v1/spaces/s-1"),
    ("create_space", {"spaceName": "새 스페이스"}, "POST", f"/rd/{D}/api/v1/spaces"),
    ("delete_space", {"spaceId": "s-1"}, "DELETE", f"/rd/{D}/api/v1/spaces/s-1"),
    ("list_projects", {"spaceId": "s-1"}, "GET", f"/rd/{D}/api/v1/projects"),
    ("get_project", {"projectId": "p-1"}, "GET", f"/rl/{I}/api/v1/projects/p-1"),
    ("create_project", {"spaceId": "s-1", "projectName": "새 프로젝트"}, "POST", f"/rd/{D}/api/v1/projects"),
    ("delete_project", {"projectId": "p-1"}, "DELETE", f"/rl/{I}/api/v1/projects/p-1"),
    ("list_tasks", {"projectId": "p-1"}, "GET", f"/rd/{D}/api/v1/tasks"),
    ("get_task", {"taskId": "t-1"}, "GET", f"/rd/{D}/api/v1/tasks/t-1"),
    ("create_task", {"projectId": "p-1", "title": "새 태스크"}, "POST", f"/rd/{D}/api/v1/tasks"),
    ("update_task_content", {"taskId": "t-1", "htmlText": "<p>수정</p>"}, "POST", f"/rd/{D}/api/v1/tasks/t-1/content"),
    ("delete_task", {"taskId": "t-1"}, "DELETE", f"/rd/{D}/api/v1/tasks/t-1"),
]
DATA_TOOL_IDS = [t[0] for t in DATA_TOOLS]

REST_ROUTES = [
    # (method, url, json body, upstream method, upstream path)
    ("GET", "/api/v1/spaces", None, "GET", f"/rd/{D}/api/v1/spaces"),
    ("GET", "/api/v1/spaces/s-1", None, "GET", f"/rd/{D}/api/v1/spaces/s-1"),
    ("POST", "/api/v1/spaces", {"spaceName": "새 스페이스"}, "POST", f"/rd/{D}/api/v1/spaces"),
    ("DELETE", "/api/v1/spaces/s-1", None, "DELETE", f"/rd/{D}/api/v1/spaces/s-1"),
    ("GET", "/api/v1/projects?space_id=s-1", None, "GET", f"/rd/{D}/api/v1/projects"),
    ("GET", "/api/v1/projects/p-1", None, "GET", f"/rl/{I}/api/v1/projects/p-1"),
    ("POST", "/api/v1/projects", {"spaceId": "s-1", "projectName": "새 프로젝트"}, "POST", f"/rd/{D}/api/v1/projects"),
    ("DELETE", "/api/v1/projects/p-1", None, "DELETE", f"/rl/{I}/api/v1/projects/p-1"),
    ("GET", "/api/v1/tasks?project_id=p-1", None, "GET", f"/rd/{D}/api/v1/tasks"),
    ("GET", "/api/v1/tasks/t-1", None, "GET", f"/rd/{D}/api/v1/tasks/t-1"),
    ("POST", "/api/v1/tasks", {"projectId": "p-1", "title": "새 태스크"}, "POST", f"/rd/{D}/api/v1/tasks"),
    ("PUT", "/api/v1/tasks/t-1/content", {"htmlText": "<p>수정</p>"}, "POST", f"/rd/{D}/api/v1/tasks/t-1/content"),
    ("DELETE", "/api/v1/tasks/t-1", None, "DELETE", f"/rd/{D}/api/v1/tasks/t-1"),
]
REST_IDS = [f"{r[0]} {r[1]}" for r in REST_ROUTES]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def cookie_headers(c):
    return {"X-Naverworks-Cookie": c} if c else {}


def mcp_call(client, name, args=None, cookie_value=None, **kw):
    r = client.post("/mcp/call", json={"name": name, "arguments": args or {}}, headers=cookie_headers(cookie_value), **kw)
    assert r.status_code == 200, r.text
    return r.json()


def _assert_single_target_call(calls):
    """대상 요청 1회. 단, 쓰기 요청(create_task, delete_project)은 프로젝트의 rl 확인용 조회 1회가 앞설 수 있음.
    모든 요청은 호출한 사용자의 쿠키로만 나가야 함."""
    assert 1 <= len(calls) <= 2, calls
    if len(calls) == 2:
        assert calls[0]["method"] == "GET" and "/api/v1/projects/" in calls[0]["path"], calls[0]
    assert len({c["cookie"] for c in calls}) == 1


def result_payload(result):
    text = result["content"][0]["text"]
    try:
        return json.loads(text)
    except ValueError:
        return text


def owner_of(payload):
    """mock_upstream 응답에 담긴 owner(요청 쿠키) 추출"""
    if isinstance(payload, list):
        payload = payload[0]
    if isinstance(payload.get("task"), dict):  # REST 원본 응답 {"task": {...}}
        payload = payload["task"]
    for key in ("spaceName", "projectName", "title"):
        if key in payload:
            return payload[key].removeprefix("owner:")
    return payload.get("owner")


def open_session(cookie_value=None) -> str:
    """SSE 핸드셰이크와 동일하게 세션을 등록합니다. (스트림을 유지하지 않고 /messages 동작만 검증)"""
    sid = f"test-{os.urandom(6).hex()}"
    session_manager._sessions[sid] = MCPSession(session_id=sid, queue=asyncio.Queue(maxsize=100), cookie_override=cookie_value)
    return sid


def close_session(sid):
    session_manager._sessions.pop(sid, None)


def rpc(client, sid, method, params=None, req_id=1, headers=None):
    body = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}
    return client.post(f"/messages?session_id={sid}", json=body, headers=headers or {})


def sse_responses(sid):
    """세션의 SSE 큐에 적재된 JSON-RPC 응답을 모두 꺼냅니다."""
    q = session_manager._sessions[sid].queue
    out = []
    while not q.empty():
        out.append(json.loads(q.get_nowait()))
    return out


def rpc_tool(client, sid, name, args=None, headers=None):
    r = rpc(client, sid, "tools/call", {"name": name, "arguments": args or {}}, headers=headers)
    assert r.status_code == 202, r.text
    responses = sse_responses(sid)
    assert len(responses) == 1, responses
    return responses[0]["result"]


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def server_has_credentials(monkeypatch):
    """서버 호스트에 운영자 본인의 쿠키(로컬 파일 + 환경 변수)가 존재하는 상황"""
    write_netscape_cookie_file(config.COOKIE_JAR_PATH, SERVER_OWNER)
    monkeypatch.setenv("NAVERWORKS_COOKIE", SERVER_OWNER)
    monkeypatch.setenv("NAVERWORKS_COOKIE_PATH", config.COOKIE_JAR_PATH)


# ---------------------------------------------------------------------------
# R1. 쿠키 미제공 사용자는 차단 — 서버 자격 증명으로 대체되지 않음
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool,args,_m,_p", DATA_TOOLS, ids=DATA_TOOL_IDS)
def test_mcp_tool_without_cookie_is_rejected(client, mock_upstream, server_has_credentials, tool, args, _m, _p):
    result = mcp_call(client, tool, args)
    assert result["isError"] is True
    assert result_payload(result)["error"] == "UNAUTHORIZED"
    assert mock_upstream == []


@pytest.mark.parametrize("method,url,body,_m,_p", REST_ROUTES, ids=REST_IDS)
def test_rest_without_cookie_is_rejected(client, mock_upstream, server_has_credentials, method, url, body, _m, _p):
    r = client.request(method, url, json=body)
    assert r.status_code == 401
    assert mock_upstream == []


def test_get_auth_status_without_cookie_is_unauthenticated(client, server_has_credentials):
    status = result_payload(mcp_call(client, "get_auth_status"))
    assert status["isAuthenticated"] is False
    assert status["cookieSource"] == "none"
    assert status["cookiePath"] is None


def test_unknown_auth_mode_fails_safe_to_multi_user(monkeypatch, server_has_credentials):
    monkeypatch.setattr(config, "AUTH_MODE", "typo-mode")
    assert config.is_local_mode() is False
    assert cookie.get_cookie_header() == ""


# ---------------------------------------------------------------------------
# R2. 모든 CRUD 요청은 호출한 사용자의 쿠키로만 업스트림 호출
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("tool,args,up_method,up_path", DATA_TOOLS, ids=DATA_TOOL_IDS)
def test_mcp_crud_forwards_callers_cookie(client, mock_upstream, server_has_credentials, tool, args, up_method, up_path):
    result = mcp_call(client, tool, args, cookie_value=USER_A)
    assert result["isError"] is False, result
    _assert_single_target_call(mock_upstream)
    call = mock_upstream[-1]
    assert (call["method"], call["path"], call["cookie"]) == (up_method, up_path, USER_A)
    if up_method == "GET":
        assert owner_of(result_payload(result)) == USER_A


@pytest.mark.parametrize("method,url,body,up_method,up_path", REST_ROUTES, ids=REST_IDS)
def test_rest_crud_forwards_callers_cookie(client, mock_upstream, server_has_credentials, method, url, body, up_method, up_path):
    r = client.request(method, url, json=body, headers=cookie_headers(USER_A))
    assert r.status_code == 200, r.text
    _assert_single_target_call(mock_upstream)
    call = mock_upstream[-1]
    assert (call["method"], call["path"], call["cookie"]) == (up_method, up_path, USER_A)


def test_create_task_payload_is_built_from_arguments(client, mock_upstream):
    mcp_call(client, "create_task", {"projectId": "p-1", "title": "제목", "htmlText": "<p>본문</p>", "parentTaskId": "t-0"}, cookie_value=USER_A)
    body = mock_upstream[-1]["json"]
    assert body["projectId"] == "p-1"
    assert body["title"] == "제목"
    assert body["content"]["htmlText"] == "<p>본문</p>"
    assert body["parentTaskId"] == "t-0"
    assert body["projectTaskParameters"][0]["taggedProjectKey"]["projectId"] == "p-1"


def test_bearer_authorization_header_is_accepted(client, mock_upstream):
    r = client.post("/mcp/call", json={"name": "list_spaces", "arguments": {}}, headers={"Authorization": f"Bearer {USER_A}"})
    assert r.json()["isError"] is False
    assert mock_upstream[0]["cookie"] == USER_A


# ---------------------------------------------------------------------------
# R3. 동시 요청 / 세션 / 캐시 격리
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_concurrent_users_never_see_each_others_data(mock_upstream):
    users = [f"WORKS_SES=user-{i:03d}-session-abcdefghij; WORKS_USER_ID=u{i}" for i in range(50)]
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        async def one(u, i):
            if i % 3 == 0:
                r = await c.get("/api/v1/tasks/t-1", headers=cookie_headers(u))
                return u, r.json()
            tool = "list_spaces" if i % 3 == 1 else "get_task"
            args = {} if tool == "list_spaces" else {"taskId": "t-1"}
            r = await c.post("/mcp/call", json={"name": tool, "arguments": args}, headers=cookie_headers(u))
            return u, result_payload(r.json())

        results = await asyncio.gather(*(one(u, i) for i, u in enumerate(users)))

    for u, payload in results:
        assert owner_of(payload) == u
    assert len(mock_upstream) == len(users)
    assert all(call["cookie"] in users for call in mock_upstream)


def test_cache_is_isolated_between_users_with_common_cookie_prefix(client, mock_upstream):
    # 실제 쿠키 파일은 host/name 순으로 정렬되어, 앞부분이 모든 사용자에게 동일한 쿠키로 시작할 수 있다.
    common = "WORKS_LOGIN_LANG=ko_KR; WORKS_CLIENT=web; "
    a = common + "WORKS_SES=aaaa-session-0000000001"
    b = common + "WORKS_SES=bbbb-session-0000000002"
    pa = result_payload(mcp_call(client, "list_spaces", cookie_value=a))
    pb = result_payload(mcp_call(client, "list_spaces", cookie_value=b))
    assert owner_of(pa) == a
    assert owner_of(pb) == b, "다른 사용자의 캐시된 스페이스 목록이 반환됨"


def test_cache_hit_for_same_user(client, mock_upstream):
    mcp_call(client, "list_spaces", cookie_value=USER_A)
    mcp_call(client, "list_spaces", cookie_value=USER_A)
    assert len(mock_upstream) == 1


def test_sse_handshake_binds_cookie_to_session(client):
    with client.stream("GET", "/sse", headers=cookie_headers(USER_A)) as r:
        first = next(line for line in r.iter_lines() if line.startswith("data:"))
        sid = first.split("session_id=")[1].split("&")[0]
        assert session_manager._sessions[sid].cookie_override == USER_A


def test_sse_sessions_are_isolated(client, mock_upstream):
    sa, sb, anon = open_session(USER_A), open_session(USER_B), open_session(None)
    try:
        ra = rpc_tool(client, sa, "list_spaces")
        rb = rpc_tool(client, sb, "list_spaces")
        rn = rpc_tool(client, anon, "list_spaces")
        assert owner_of(result_payload(ra)) == USER_A
        assert owner_of(result_payload(rb)) == USER_B
        assert rn["isError"] is True and result_payload(rn)["error"] == "UNAUTHORIZED"
        assert [c["cookie"] for c in mock_upstream] == [USER_A, USER_B]
    finally:
        for s in (sa, sb, anon):
            close_session(s)


def test_set_user_cookie_applies_only_to_own_session(client, mock_upstream):
    s1, s2 = open_session(None), open_session(None)
    try:
        res = rpc_tool(client, s1, "set_user_cookie", {"cookie": USER_A})
        assert res["isError"] is False
        assert owner_of(result_payload(rpc_tool(client, s1, "list_spaces"))) == USER_A
        # 같은 세션의 후속 요청에서도 유지
        assert owner_of(result_payload(rpc_tool(client, s1, "get_task", {"taskId": "t-1"}))) == USER_A
        # 다른 세션에는 영향 없음
        other = rpc_tool(client, s2, "list_spaces")
        assert result_payload(other)["error"] == "UNAUTHORIZED"
    finally:
        close_session(s1)
        close_session(s2)


def test_set_user_cookie_replaces_previous_cookie_in_session(client, mock_upstream):
    s = open_session(USER_A)
    try:
        rpc_tool(client, s, "set_user_cookie", {"cookie": USER_B})
        assert owner_of(result_payload(rpc_tool(client, s, "list_spaces"))) == USER_B
    finally:
        close_session(s)


def test_per_message_header_overrides_only_that_message(client, mock_upstream):
    s = open_session(USER_A)
    try:
        r1 = rpc_tool(client, s, "get_task", {"taskId": "t-1"}, headers=cookie_headers(USER_B))
        r2 = rpc_tool(client, s, "get_task", {"taskId": "t-1"})
        assert owner_of(result_payload(r1)) == USER_B
        assert owner_of(result_payload(r2)) == USER_A
    finally:
        close_session(s)


def test_messages_for_unknown_or_closed_session_are_rejected(client, mock_upstream):
    s = open_session(USER_A)
    close_session(s)
    r = rpc(client, s, "tools/call", {"name": "list_spaces", "arguments": {}})
    assert r.status_code == 404
    assert mock_upstream == []


def test_stateless_http_set_user_cookie_does_not_leak_to_next_request(client, mock_upstream):
    mcp_call(client, "set_user_cookie", {"cookie": USER_A})
    result = mcp_call(client, "list_spaces")
    assert result_payload(result)["error"] == "UNAUTHORIZED"
    assert mock_upstream == []


# ---------------------------------------------------------------------------
# R4. 익명 사용자가 서버 호스트의 자격 증명을 사용할 수 없음
# ---------------------------------------------------------------------------

def test_cookie_path_header_cannot_read_server_files(client, mock_upstream, server_has_credentials):
    r = client.post(
        "/mcp/call",
        json={"name": "list_spaces", "arguments": {}},
        headers={"X-Naverworks-Cookie-Path": config.COOKIE_JAR_PATH},
    )
    assert result_payload(r.json())["error"] == "UNAUTHORIZED"
    assert mock_upstream == []


def test_cookie_path_query_cannot_read_server_files(client, mock_upstream, server_has_credentials):
    r = client.get(f"/api/v1/spaces?cookie_path={config.COOKIE_JAR_PATH}")
    assert r.status_code == 401
    assert mock_upstream == []


def test_set_user_cookie_with_server_path_is_refused(client, mock_upstream, server_has_credentials):
    s = open_session(None)
    try:
        res = rpc_tool(client, s, "set_user_cookie", {"cookiePath": config.COOKIE_JAR_PATH})
        assert res["isError"] is True
        assert session_manager._sessions[s].cookie_override is None
        after = rpc_tool(client, s, "list_spaces")
        assert result_payload(after)["error"] == "UNAUTHORIZED"
        assert mock_upstream == []
    finally:
        close_session(s)


def test_login_tool_returns_manual_guide_without_server_browser(client, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("익명 사용자 요청으로 서버 호스트에서 브라우저 로그인이 실행됨")

    monkeypatch.setattr(cookie, "login_via_browser", boom)
    monkeypatch.setattr("app.core.mcp_spec.login_via_browser", boom)

    tools = client.post("/mcp/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).json()["result"]["tools"]
    login = next(t for t in tools if t["name"] == "login_naverworks")
    assert "set_user_cookie" in login["description"]
    assert login["inputSchema"]["properties"] == {}
    assert "login_naverworks" in [t["name"] for t in client.get("/mcp/tools").json()["tools"]]

    # 쿠키가 없어도(익명) 안내는 받을 수 있어야 함
    for cookie_value in (None, USER_A):
        result = mcp_call(client, "login_naverworks", {"timeoutSeconds": 1}, cookie_value=cookie_value)
        assert result["isError"] is False
        guide = result_payload(result)
        assert guide["action"] == "MANUAL_LOGIN_REQUIRED"
        assert guide["loginUrl"] == config.BASE_URL
        assert guide["nextTool"] == "set_user_cookie"


def test_unauthorized_points_to_login_tool(client):
    result = mcp_call(client, "list_spaces", {}, cookie_value=None)
    payload = result_payload(result)
    assert payload["error"] == "UNAUTHORIZED"
    assert payload["nextTool"] == "login_naverworks"


@pytest.mark.parametrize("path", ["/auth/refresh-cookie", "/auth/browser-login"])
def test_server_credential_endpoints_are_disabled(client, monkeypatch, path):
    def boom(*a, **k):
        raise AssertionError("익명 요청으로 서버 호스트 키체인/브라우저 접근이 실행됨")

    monkeypatch.setattr("app.api.system.refresh_cookie_jar", boom)
    monkeypatch.setattr("app.api.system.login_via_browser", boom)
    r = client.post(path)
    assert r.status_code == 403


def test_local_mode_still_supports_cookie_path_and_login_tool(client, local_mode, mock_upstream):
    write_netscape_cookie_file(config.COOKIE_JAR_PATH, USER_A)
    r = client.post("/mcp/call", json={"name": "list_spaces", "arguments": {}},
                    headers={"X-Naverworks-Cookie-Path": config.COOKIE_JAR_PATH})
    assert owner_of(result_payload(r.json())) == USER_A
    assert "login_naverworks" in [t["name"] for t in client.get("/mcp/tools").json()["tools"]]


def test_stdio_server_defaults_to_local_mode(tmp_path):
    """stdio 서버는 사용자 본인 PC에서 실행되는 단일 사용자용이므로 로컬 모드가 기본이어야 합니다."""
    jar = tmp_path / "jar.txt"
    write_netscape_cookie_file(str(jar), USER_A)
    env = {k: v for k, v in os.environ.items() if not k.startswith("NAVERWORKS_")}
    env["NAVERWORKS_COOKIE_JAR_PATH"] = str(jar)
    reqs = "\n".join(json.dumps(r) for r in [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "get_auth_status", "arguments": {}}},
    ]) + "\n"
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = subprocess.run([sys.executable, os.path.join(root, "apps", "server.py")], input=reqs, capture_output=True,
                         text=True, env=env, timeout=30).stdout.strip().splitlines()
    tools = [t["name"] for t in json.loads(out[0])["result"]["tools"]]
    status = json.loads(json.loads(out[1])["result"]["content"][0]["text"])
    assert "login_naverworks" in tools
    assert status["cookieSource"] == "local_cookie_jar"


# ---------------------------------------------------------------------------
# R5. 사용자 쿠키가 접근 로그에 남지 않음
# ---------------------------------------------------------------------------

def test_access_log_redacts_cookie_query(client):
    from app.main import RedactCookieQueryFilter

    access_logger = logging.getLogger("uvicorn.access")
    assert any(isinstance(f, RedactCookieQueryFilter) for f in access_logger.filters)

    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, __file__, 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "GET", "/sse?x=1&cookie=WORKS_SES%3Dtop-secret&y=2", "1.1", 200), None,
    )
    assert RedactCookieQueryFilter().filter(record) is True
    msg = record.getMessage()
    assert "top-secret" not in msg
    assert "x=1" in msg and "y=2" in msg


# ---------------------------------------------------------------------------
# 태스크 생성자 = 요청 쿠키의 사용자 (다른 사람의 사용자 ID를 싣지 않음)
# ---------------------------------------------------------------------------

def _all_keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _all_keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_keys(v)


def test_create_task_tool_sends_no_action_user_id(client, mock_upstream):
    mcp_call(client, "create_task", {"projectId": "p-1", "title": "t"}, cookie_value=USER_A)
    body = mock_upstream[-1]["json"]
    assert "actionUserId" not in set(_all_keys(body))
    assert body["projectTaskParameters"][0]["taggedProjectKey"] == {"rl": I, "domainId": D, "projectId": "p-1"}


def test_create_task_tool_schema_has_no_action_user_id(client):
    tools = {t["name"]: t for t in client.get("/mcp/tools").json()["tools"]}
    assert "actionUserId" not in tools["create_task"]["inputSchema"]["properties"]


def test_rest_create_task_ignores_legacy_action_user_id(client, mock_upstream):
    r = client.post("/api/v1/tasks", json={"projectId": "p-1", "title": "t", "actionUserId": "100001507091259"},
                    headers=cookie_headers(USER_A))
    assert r.status_code == 200
    assert "actionUserId" not in set(_all_keys(mock_upstream[-1]["json"]))
