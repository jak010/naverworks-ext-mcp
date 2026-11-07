import json
import os

# 기존 테스트는 "운영자가 NAVERWORKS_DOMAIN_ID 를 설정한 서버" 기준으로 경로를 검증합니다.
# (설정이 없을 때의 동적 탐색은 tests/test_domain_discovery.py 에서 검증)
os.environ.setdefault("NAVERWORKS_DOMAIN_ID", "300098158")

import httpx
import pytest

from app import config
from app.core import cookie, client as nw_client
from app.core.mcp_spec import invalidate_mcp_cache
from app.core.ids import clear_rl_cache, clear_user_domains


@pytest.fixture(autouse=True)
def isolated_cookie_env(tmp_path, monkeypatch):
    """테스트가 실제 사용자 쿠키 파일/환경 변수를 읽어 네이버웍스에 실제 요청을 보내지 않도록 격리합니다.
    기본 인증 모드는 서비스 운영 모드인 multi_user 입니다."""
    monkeypatch.delenv("NAVERWORKS_COOKIE", raising=False)
    monkeypatch.delenv("NAVERWORKS_COOKIE_PATH", raising=False)
    monkeypatch.setattr(config, "COOKIE_JAR_PATH", str(tmp_path / "proj_cookies.txt"))
    monkeypatch.setattr(config, "AUTH_MODE", "multi_user", raising=False)
    # 기존 익명 /mcp/rpc 테스트는 OAuth 401 없이 동작을 검증 (OAuth 흐름은 tests/test_oauth.py에서 켜고 검증)
    monkeypatch.setattr(config, "OAUTH_ENABLED", False, raising=False)
    monkeypatch.setattr(cookie, "_jar_cache", None)
    invalidate_mcp_cache()
    clear_rl_cache()
    clear_user_domains()
    yield
    invalidate_mcp_cache()
    clear_rl_cache()
    clear_user_domains()


@pytest.fixture
def local_mode(monkeypatch):
    """로컬 단일 사용자 모드 (stdio / CLI / 개인 PC 실행)
    TestClient의 기본 Host(testserver)를 local 모드 허용 호스트에 추가합니다."""
    monkeypatch.setattr(config, "AUTH_MODE", "local", raising=False)
    monkeypatch.setattr(config, "LOCAL_ALLOWED_HOSTS", config.LOCAL_ALLOWED_HOSTS | {"testserver"})


def write_netscape_cookie_file(path: str, cookie_str: str) -> None:
    lines = ["# Netscape HTTP Cookie File"]
    for pair in cookie_str.split("; "):
        name, val = pair.split("=", 1)
        lines.append("\t".join([".worksmobile.com", "TRUE", "/", "TRUE", "2147483647", name, val]))
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


@pytest.fixture
def mock_upstream(monkeypatch):
    """네이버웍스 업스트림을 MockTransport로 대체합니다.
    - 수신한 요청(method, path, params, cookie, json)을 기록합니다.
    - 응답 데이터의 이름 필드에 요청 쿠키를 그대로 담아(owner) 반환하므로,
      어떤 사용자의 쿠키로 조회된 데이터인지 응답만 보고 판별할 수 있습니다."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        owner = request.headers.get("cookie")
        body = json.loads(request.content) if request.content else None
        path = request.url.path
        calls.append({
            "method": request.method,
            "path": path,
            "params": dict(request.url.params),
            "cookie": owner,
            "json": body,
        })
        if request.method == "GET":
            if path.endswith("/spaces"):
                return httpx.Response(200, json=[{"spaceId": "s-1", "spaceName": f"owner:{owner}"}])
            if "/spaces/" in path:
                return httpx.Response(200, json={"spaceId": "s-1", "spaceName": f"owner:{owner}"})
            if path.endswith("/projects"):
                return httpx.Response(200, json=[{"projectId": "p-1", "projectName": f"owner:{owner}"}])
            if "/projects/" in path:
                return httpx.Response(200, json={"project": {"projectId": "p-1", "projectName": f"owner:{owner}"}})
            if path.endswith("/tasks"):
                return httpx.Response(200, json={"projectTasks": [{"taskId": "t-1", "title": f"owner:{owner}"}]})
            if "/tasks/" in path:
                # 실제 응답 구조: {"task": {...}, "relatedUserIds": [...]}
                return httpx.Response(200, json={"task": {"taskId": "t-1", "title": f"owner:{owner}"}, "relatedUserIds": []})
        return httpx.Response(200, json={"ok": True, "owner": owner})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake_get_async_client():
        return mock_client

    monkeypatch.setattr(nw_client, "get_async_client", fake_get_async_client)
    return calls
