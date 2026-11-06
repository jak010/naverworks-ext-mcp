"""네트워크 노출 보호 검증

local 모드는 쿠키 없는 요청에 서버 호스트(사용자 본인)의 네이버웍스 쿠키를 사용하므로,
사용자가 방문한 악성 웹페이지가 브라우저로 localhost 서버를 호출해 데이터를 읽거나 지우지 못해야 합니다.
"""

import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from tests.conftest import write_netscape_cookie_file

OWNER = "WORKS_SES=local-owner-session-0000001; WORKS_USER_ID=owner"
EVIL = "http://evil.example"


@pytest.fixture
def local_client(local_mode, mock_upstream):
    write_netscape_cookie_file(config.COOKIE_JAR_PATH, OWNER)
    with TestClient(app, base_url="http://localhost:9050") as c:
        yield c


# --- CORS ------------------------------------------------------------------

def test_no_cors_headers_for_cross_origin_by_default(mock_upstream):
    with TestClient(app) as c:
        r = c.get("/health", headers={"Origin": EVIL})
        pre = c.options("/api/v1/spaces", headers={"Origin": EVIL, "Access-Control-Request-Method": "DELETE"})
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-origin" not in pre.headers


def test_cors_allowlist_is_configurable():
    """CORS_ALLOW_ORIGINS로 지정한 Origin만 허용 (credentials 미허용)"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    code = (
        "from fastapi.testclient import TestClient; from app.main import app; c=TestClient(app);"
        "ok=c.options('/mcp/call', headers={'Origin':'https://app.example','Access-Control-Request-Method':'POST'});"
        "bad=c.options('/mcp/call', headers={'Origin':'http://evil.example','Access-Control-Request-Method':'POST'});"
        "print(ok.headers.get('access-control-allow-origin'), bad.headers.get('access-control-allow-origin'), ok.headers.get('access-control-allow-credentials'))"
    )
    env = dict(os.environ, CORS_ALLOW_ORIGINS="https://app.example", NAVERWORKS_AUTH_MODE="multi_user")
    out = subprocess.run([sys.executable, "-c", code], cwd=os.path.join(root, "apps"), env=env, capture_output=True, text=True, timeout=30)
    assert out.stdout.split()[-3:] == ["https://app.example", "None", "None"], out.stderr


# --- 바인드 기본값 -------------------------------------------------------------

def _config_host(**env_overrides):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {k: v for k, v in os.environ.items() if k not in ("HOST", "NAVERWORKS_AUTH_MODE")}
    env.update(env_overrides)
    out = subprocess.run([sys.executable, "-c", "from app import config; print(config.HOST)"],
                         cwd=os.path.join(root, "apps"), env=env, capture_output=True, text=True, timeout=30)
    return out.stdout.strip()


@pytest.mark.parametrize("mode,expected", [("local", "127.0.0.1"), ("multi_user", "0.0.0.0")])
def test_default_bind_host_depends_on_mode(mode, expected):
    assert _config_host(NAVERWORKS_AUTH_MODE=mode) == expected


def test_explicit_host_env_wins():
    assert _config_host(NAVERWORKS_AUTH_MODE="local", HOST="0.0.0.0") == "0.0.0.0"


# --- local 모드 Host / Origin 검증 ---------------------------------------------

def test_local_same_origin_requests_allowed(local_client, mock_upstream):
    assert local_client.get("/api/v1/spaces").status_code == 200
    r = local_client.post("/mcp/call", json={"name": "list_spaces", "arguments": {}}, headers={"Origin": "http://localhost:9050"})
    assert r.status_code == 200 and r.json()["isError"] is False
    assert [c["cookie"] for c in mock_upstream] == [OWNER, OWNER]


@pytest.mark.parametrize("method,url,body", [
    ("GET", "/api/v1/spaces", None),
    ("DELETE", "/api/v1/spaces/s-1", None),
    ("POST", "/mcp/call", {"name": "delete_task", "arguments": {"taskId": "t-1"}}),
])
def test_local_cross_origin_page_is_blocked(local_client, mock_upstream, method, url, body):
    r = local_client.request(method, url, json=body, headers={"Origin": EVIL})
    assert r.status_code == 403
    assert mock_upstream == [], "악성 페이지 요청이 사용자 쿠키로 네이버웍스에 전달됨"


def test_local_text_plain_simple_request_is_blocked(local_client, mock_upstream):
    """CORS preflight 없이 보낼 수 있는 단순 요청(text/plain POST)도 차단"""
    r = local_client.post("/mcp/call", content=b'{"name":"delete_space","arguments":{"spaceId":"s-1"}}',
                          headers={"Origin": EVIL, "Content-Type": "text/plain"})
    assert r.status_code == 403
    assert mock_upstream == []


def test_local_dns_rebinding_host_is_blocked(local_client, mock_upstream):
    """공격자 도메인이 127.0.0.1로 재바인딩되어 같은 출처로 위장한 경우 (Host 헤더가 공격자 도메인)"""
    r = local_client.get("/api/v1/spaces", headers={"Host": "evil.example:9050"})
    assert r.status_code == 403
    assert mock_upstream == []


def test_local_null_origin_is_blocked(local_client, mock_upstream):
    r = local_client.get("/api/v1/spaces", headers={"Origin": "null"})
    assert r.status_code == 403


def test_local_ipv6_loopback_allowed(local_client):
    assert local_client.get("/health", headers={"Host": "[::1]:9050"}).status_code == 200


def test_multi_user_mode_does_not_restrict_host(mock_upstream):
    """다중 사용자 서비스는 외부 도메인으로 서비스되므로 Host 제한 없음 (인증은 사용자 쿠키 헤더로만)"""
    with TestClient(app, base_url="http://mcp.example.com") as c:
        assert c.get("/health").status_code == 200
        assert c.get("/api/v1/spaces").status_code == 401
