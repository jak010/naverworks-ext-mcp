"""조직 ID(domainId) 기본값 없이 동작 검증 (NAVERWORKS_DOMAIN_ID 미설정)

- ID가 있는 호출: ID에서 추출하고 사용자별로 기억
- ID 없는 진입점(list_spaces 등): 기억한 값 → 로그인한 웹 페이지(/space)에서 추출 → 실패 시 DOMAIN_ID_UNKNOWN
- 사용자(쿠키)마다 따로 기억
- OAuth 로그인 검증도 조직 기본값 없이 동작
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.core import client as nw_client
from app.main import app

OD = "777000111"
A = "WORKS_SES=disc-user-a-0001; WORKS_USER_ID=a"
B = "WORKS_SES=disc-user-b-0002; WORKS_USER_ID=b"
SPACE = f"s-{OD}-4400b350-7c86-40db-b5cb-9813fcbfac1a"

# Next.js 서버 렌더링 데이터처럼 따옴표가 이스케이프된 페이지
PAGE_WITH_DOMAIN = f'<html><script>self.__next_f.push([1,"{{\\"user\\":{{\\"domainId\\":\\"{OD}\\",\\"name\\":\\"a\\"}}}}"])</script></html>'


@pytest.fixture(autouse=True)
def no_default_domain(monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_DOMAIN_ID", "")


def make_upstream(monkeypatch, page=PAGE_WITH_DOMAIN, page_status=200, location=None):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path, req.headers.get("cookie")))
        if req.url.path == "/space":
            headers = {"location": location} if location else {}
            return httpx.Response(page_status, text=page, headers=headers)
        if req.url.path.endswith("/spaces"):
            return httpx.Response(200, json=[{"spaceId": SPACE, "spaceName": "S"}])
        return httpx.Response(200, json={"spaceId": SPACE, "spaceName": "S"})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    return calls


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def call(client, name, args, cookie=A):
    r = client.post("/mcp/call", json={"name": name, "arguments": args}, headers={"X-Naverworks-Cookie": cookie})
    assert r.status_code == 200, r.text
    return r.json()


def page_fetches(calls, cookie=None):
    return [c for c in calls if c[1] == "/space" and (cookie is None or c[2] == cookie)]


def test_entry_point_discovers_domain_from_logged_in_page_once(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    assert call(client, "list_spaces", {})["isError"] is False
    assert ("GET", f"/rd/{OD}/api/v1/spaces", A) in calls
    call(client, "create_space", {"spaceName": "새 스페이스"})
    assert ("POST", f"/rd/{OD}/api/v1/spaces", A) in calls
    assert len(page_fetches(calls)) == 1  # 두 번째부터는 기억한 값


def test_domain_learned_from_ids_skips_page(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    call(client, "get_space", {"spaceId": SPACE})
    call(client, "list_spaces", {})
    assert ("GET", f"/rd/{OD}/api/v1/spaces", A) in calls
    assert page_fetches(calls) == []


def test_domain_is_remembered_per_user(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    call(client, "get_space", {"spaceId": SPACE}, cookie=A)
    call(client, "list_spaces", {}, cookie=B)
    assert page_fetches(calls, A) == [] and len(page_fetches(calls, B)) == 1


def test_unknown_domain_asks_for_id(client, monkeypatch):
    calls = make_upstream(monkeypatch, page="<html>no org info</html>")
    res = call(client, "list_spaces", {})
    assert res["isError"] is True
    assert json.loads(res["content"][0]["text"])["error"] == "DOMAIN_ID_UNKNOWN"
    assert not any("/rd/" in c[1] for c in calls)  # 엉뚱한 조직으로 요청하지 않음

    r = client.get("/api/v1/spaces", headers={"X-Naverworks-Cookie": A})
    assert r.status_code == 400 and r.json()["error"] == "DOMAIN_ID_UNKNOWN"


def test_env_value_used_when_set(client, monkeypatch):
    monkeypatch.setattr(config, "DEFAULT_DOMAIN_ID", "123456")
    calls = make_upstream(monkeypatch)
    call(client, "list_spaces", {})
    assert ("GET", "/rd/123456/api/v1/spaces", A) in calls and page_fetches(calls) == []


def test_rest_list_spaces_uses_discovery(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    assert client.get("/api/v1/spaces", headers={"X-Naverworks-Cookie": A}).status_code == 200
    assert ("GET", f"/rd/{OD}/api/v1/spaces", A) in calls


# ---------------------------------------------------------------------------
# OAuth 로그인 검증 (조직 기본값 없이)
# ---------------------------------------------------------------------------

REDIRECT = "http://127.0.0.1:19876/callback"


def submit_login(client, cookie):
    cid = client.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).json()["client_id"]
    params = {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
              "code_challenge": "x" * 43, "code_challenge_method": "S256", "state": "s"}
    return client.post("/oauth/authorize", data={**params, "cookie": cookie}, follow_redirects=False)


def test_oauth_login_validates_and_learns_domain(client, monkeypatch):
    monkeypatch.setattr(config, "OAUTH_ENABLED", True)
    calls = make_upstream(monkeypatch)
    assert submit_login(client, A).status_code == 303
    assert ("GET", f"/rd/{OD}/api/v1/spaces", A) in calls
    calls.clear()
    call(client, "list_spaces", {})
    assert page_fetches(calls) == []  # 로그인 때 알아낸 조직 ID 재사용


def test_oauth_login_rejects_cookie_redirected_to_login(client, monkeypatch):
    monkeypatch.setattr(config, "OAUTH_ENABLED", True)
    calls = make_upstream(monkeypatch, page="", page_status=307, location="/login/login?accessUrl=x")
    r = submit_login(client, A)
    assert r.status_code == 400 and "거부" in r.text
    assert not any("/rd/" in c[1] for c in calls)


# ---------------------------------------------------------------------------
# 로그인 때 "Copy as cURL"로 쿠키와 조직 ID를 함께 받기
# ---------------------------------------------------------------------------

from app.api.oauth import parse_login_input  # noqa: E402
from app.core.cookie import parse_access_token  # noqa: E402
from app.core.ids import clear_user_domains  # noqa: E402

COOKIE = "NNB=abc; WORKS_SES=curl-session-0001; WORKS_USER_ID=c"
URL = f"https://project.worksmobile.com/rd/{OD}/api/v1/spaces"


@pytest.mark.parametrize("pasted", [
    f"curl '{URL}' \\\n  -H 'accept: application/json' \\\n  -b '{COOKIE}' \\\n  -H 'user-agent: x'",   # Chrome bash (-b)
    f"curl '{URL}' \\\n  -H 'accept: */*' \\\n  -H 'cookie: {COOKIE}'",                              # 이전 Chrome bash (-H cookie)
    f'curl ^"{URL}^" ^\n  -H ^"accept: */*^" ^\n  -b ^"{COOKIE}^"',                                   # Windows cmd
])
def test_parse_login_input(pasted):
    assert parse_login_input(pasted) == (COOKIE, OD)


def test_parse_powershell_copy():
    """Chrome 'Copy as PowerShell' 붙여넣기에서 쿠키와 조직 ID를 얻습니다."""
    cookie_adds = "\n".join(
        f'$session.Cookies.Add((New-Object System.Net.Cookie("{n}", "{v}", "/", ".worksmobile.com")))'
        for n, v in (pair.split("=", 1) for pair in COOKIE.split("; "))
    )
    ps = (
        "$session = New-Object Microsoft.PowerShell.Commands.WebRequestSession\n"
        f"{cookie_adds}\n"
        f'Invoke-WebRequest -UseBasicParsing -Uri "{URL}" -WebSession $session -Headers @{{"accept"="application/json"}}'
    )
    assert parse_login_input(ps) == (COOKIE, OD)


def test_parse_cookie_only_has_no_domain():
    assert parse_login_input(COOKIE) == (COOKIE, None)
    assert parse_login_input(f"cookie: {COOKIE}") == (COOKIE, None)


def login_and_get_token(client, pasted):
    import base64, hashlib, secrets
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    cid = client.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).json()["client_id"]
    params = {"response_type": "code", "client_id": cid, "redirect_uri": REDIRECT,
              "code_challenge": challenge, "code_challenge_method": "S256", "state": "s"}
    r = client.post("/oauth/authorize", data={**params, "cookie": pasted}, follow_redirects=False)
    assert r.status_code == 303, r.text
    code = r.headers["location"].split("code=")[1].split("&")[0]
    tok = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "code_verifier": verifier,
                                            "client_id": cid, "redirect_uri": REDIRECT})
    return tok.json()["access_token"]


def test_curl_login_puts_domain_in_token_and_survives_restart(client, monkeypatch):
    monkeypatch.setattr(config, "OAUTH_ENABLED", True)
    calls = make_upstream(monkeypatch, page="<html>no org info</html>")  # 웹 페이지 탐색으로는 못 찾는 상황
    token = login_and_get_token(client, f"curl '{URL}' -H 'accept: */*' -b '{COOKIE}'")
    assert parse_access_token(token) == (COOKIE, OD)
    assert page_fetches(calls) == []  # cURL에서 바로 얻어 페이지 조회 불필요

    clear_user_domains()  # 서버 재시작으로 기억이 사라진 상황
    calls.clear()
    r = client.post("/mcp/rpc", json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                      "params": {"name": "list_spaces", "arguments": {}}},
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200 and r.json()["result"]["isError"] is False
    assert ("GET", f"/rd/{OD}/api/v1/spaces", COOKIE) in calls and page_fetches(calls) == []


def test_login_without_domain_asks_for_rd_curl(client, monkeypatch):
    monkeypatch.setattr(config, "OAUTH_ENABLED", True)
    make_upstream(monkeypatch, page="<html>no org info</html>")
    r = submit_login(client, COOKIE)
    assert r.status_code == 400 and "조직 ID를 찾지 못했습니다" in r.text and "/rd/" in r.text
    assert 'name="request_url"' not in r.text


def test_domain_header_for_header_clients(client, monkeypatch):
    calls = make_upstream(monkeypatch, page="<html>no org info</html>")
    r = client.post("/mcp/call", json={"name": "list_spaces", "arguments": {}},
                    headers={"X-Naverworks-Cookie": A, "X-Naverworks-Domain-Id": OD})
    assert r.json()["isError"] is False
    assert ("GET", f"/rd/{OD}/api/v1/spaces", A) in calls and page_fetches(calls) == []
