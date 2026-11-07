"""MCP 표준 OAuth 브라우저 로그인 흐름 검증

쿠키 없이 /mcp/rpc 에 접속 → 401 + WWW-Authenticate → 메타데이터 탐색 → 클라이언트 등록
→ 브라우저 로그인 페이지(/oauth/authorize)에서 쿠키 제출 → 인가 코드 → 토큰(PKCE) → Bearer 로 도구 호출
"""

import base64
import hashlib
import secrets
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from app import config
from app.core import client as nw_client
from app.main import app

USER = "WORKS_SES=oauth-user-session; WORKS_USER_ID=oauth-user"
REDIRECT = "http://127.0.0.1:19876/mcp/oauth/callback"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "OAUTH_ENABLED", True)
    with TestClient(app) as c:
        yield c


def pkce():
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def rpc(client, method, headers=None, **params):
    return client.post("/mcp/rpc", json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, headers=headers or {})


def authorize_params(client_id, challenge):
    return {
        "response_type": "code", "client_id": client_id, "redirect_uri": REDIRECT,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": "xyz",
    }


def login(client, cookie=USER):
    client_id = client.post("/oauth/register", json={"redirect_uris": [REDIRECT]}).json()["client_id"]
    verifier, challenge = pkce()
    params = authorize_params(client_id, challenge)
    page = client.get("/oauth/authorize", params=params)
    assert page.status_code == 200 and 'name="cookie"' in page.text
    r = client.post("/oauth/authorize", data={**params, "cookie": cookie}, follow_redirects=False)
    return client_id, verifier, r


def test_missing_cookie_triggers_oauth_discovery(client):
    r = rpc(client, "initialize", protocolVersion="2025-06-18")
    assert r.status_code == 401
    assert 'resource_metadata="http://testserver/.well-known/oauth-protected-resource"' in r.headers["www-authenticate"]

    prm = client.get("/.well-known/oauth-protected-resource").json()
    assert prm["authorization_servers"] == ["http://testserver"]
    meta = client.get("/.well-known/oauth-authorization-server").json()
    assert meta["authorization_endpoint"] == "http://testserver/oauth/authorize"
    assert meta["code_challenge_methods_supported"] == ["S256"]


def test_header_cookie_skips_oauth(client, mock_upstream):
    r = rpc(client, "tools/list", headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200 and r.json()["result"]["tools"]


def test_full_browser_login_flow(client, mock_upstream):
    client_id, verifier, r = login(client)
    assert r.status_code == 303
    loc = urlsplit(r.headers["location"])
    assert f"{loc.scheme}://{loc.netloc}{loc.path}" == REDIRECT
    q = parse_qs(loc.query)
    assert q["state"] == ["xyz"]
    # 쿠키 검증 요청이 사용자 쿠키로 나갔는지
    assert mock_upstream[-1]["cookie"] == USER

    tok = client.post("/oauth/token", data={
        "grant_type": "authorization_code", "code": q["code"][0], "redirect_uri": REDIRECT,
        "client_id": client_id, "code_verifier": verifier,
    })
    assert tok.status_code == 200
    access = tok.json()["access_token"]

    # 인가 코드는 1회용
    again = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": q["code"][0], "code_verifier": verifier})
    assert again.status_code == 400

    res = rpc(client, "tools/call", headers={"Authorization": f"Bearer {access}"}, name="list_spaces", arguments={})
    assert res.status_code == 200
    assert "owner:" + USER in res.json()["result"]["content"][0]["text"]


def test_wrong_pkce_verifier_rejected(client, mock_upstream):
    client_id, _, r = login(client)
    code = parse_qs(urlsplit(r.headers["location"]).query)["code"][0]
    tok = client.post("/oauth/token", data={"grant_type": "authorization_code", "code": code, "code_verifier": "wrong" * 10})
    assert tok.status_code == 400 and tok.json()["error"] == "invalid_grant"


def test_cookie_rejected_by_naverworks_shows_form_again(client, monkeypatch):
    rejecting = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(401, json={"error": "unauthorized"})))

    async def fake():
        return rejecting

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    _, _, r = login(client)
    assert r.status_code == 400 and "거부" in r.text and 'name="cookie"' in r.text


def test_untrusted_redirect_uri_refused(client):
    _, challenge = pkce()
    params = authorize_params("nw-x", challenge)
    params["redirect_uri"] = "http://evil.example.com/cb"
    assert client.get("/oauth/authorize", params=params).status_code == 400
    assert client.post("/oauth/register", json={"redirect_uris": ["http://evil.example.com/cb"]}).status_code == 400


def test_expired_session_returns_401_for_reauth(client, monkeypatch):
    expired = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(401, json={"error": "expired"})))

    async def fake():
        return expired

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    r = rpc(client, "tools/call", headers={"Authorization": f"Bearer {USER}"}, name="get_project", arguments={"projectId": "p-1"})
    assert r.status_code == 401 and "www-authenticate" in r.headers
