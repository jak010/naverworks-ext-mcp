"""domainId / rl 동적 결정 검증

- domainId: ID(`s-/p-/t-{domainId}-{uuid}`)에서 추출 → 서버 기본값(NAVERWORKS_DOMAIN_ID)과 다른 조직도 동작
- rl: 프로젝트 응답에서 기억하고, 모르면 프로젝트 조회로 확인 → 쓰기 요청(create_task, delete_project)에 사용
- 명시한 값은 항상 우선
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_DOMAIN_ID as D, DEFAULT_INSTANCE_CODE as I
from app.core import client as nw_client
from app.core.ids import domain_from_id, resolve_domain_id
from app.main import app

USER = "WORKS_SES=dyn-user-session-0001; WORKS_USER_ID=dyn"
OD, ORL = "777000111", "99999"  # 서버 기본값과 다른 조직
SPACE = f"s-{OD}-4400b350-7c86-40db-b5cb-9813fcbfac1a"
PROJECT = f"p-{OD}-11111111-2222-3333-4444-555555555555"
TASK = f"t-{OD}-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


@pytest.fixture
def upstream(monkeypatch):
    """다른 조직(OD, ORL)의 응답을 돌려주는 업스트림"""
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        calls.append({"method": req.method, "path": path, "json": json.loads(req.content) if req.content else None})
        project = {"projectId": PROJECT, "projectName": "P", "rl": ORL, "domainId": OD}
        if req.method == "GET" and path.endswith("/projects"):
            return httpx.Response(200, json=[project])
        if req.method == "GET" and "/projects/" in path:
            return httpx.Response(200, json={"project": project})
        if req.method == "GET" and path.endswith("/spaces"):
            return httpx.Response(200, json=[{"spaceId": SPACE, "spaceName": "S", "rl": ORL, "domainId": OD}])
        return httpx.Response(200, json={"ok": True})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    return calls


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def call(client, name, args):
    r = client.post("/mcp/call", json={"name": name, "arguments": args}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200 and r.json()["isError"] is False, r.text
    return r.json()


def test_domain_from_id():
    assert domain_from_id(SPACE) == OD
    assert domain_from_id(PROJECT) == OD
    assert domain_from_id(TASK) == OD
    assert domain_from_id("s-1") is None and domain_from_id(None) is None
    assert resolve_domain_id(None, "s-1", TASK) == OD  # 파싱되는 첫 ID 사용
    assert resolve_domain_id("123", TASK) == "123"     # 명시 값 우선
    assert resolve_domain_id(None) == D                # 진입점: 서버 기본값


@pytest.mark.parametrize("tool,args,expected_path", [
    ("get_space", {"spaceId": SPACE}, f"/rd/{OD}/api/v1/spaces/{SPACE}"),
    ("delete_space", {"spaceId": SPACE}, f"/rd/{OD}/api/v1/spaces/{SPACE}"),
    ("list_projects", {"spaceId": SPACE}, f"/rd/{OD}/api/v1/projects"),
    ("create_project", {"spaceId": SPACE, "projectName": "n"}, f"/rd/{OD}/api/v1/projects"),
    ("list_tasks", {"projectId": PROJECT}, f"/rd/{OD}/api/v1/tasks"),
    ("get_task", {"taskId": TASK}, f"/rd/{OD}/api/v1/tasks/{TASK}"),
    ("update_task_content", {"taskId": TASK, "htmlText": "x"}, f"/rd/{OD}/api/v1/tasks/{TASK}/content"),
    ("delete_task", {"taskId": TASK}, f"/rd/{OD}/api/v1/tasks/{TASK}"),
])
def test_domain_id_taken_from_ids(client, upstream, tool, args, expected_path):
    call(client, tool, args)
    assert upstream[-1]["path"] == expected_path
    assert all(f"/rd/{D}/" not in c["path"] for c in upstream)


def test_create_task_resolves_rl_from_project_once(client, upstream):
    call(client, "create_task", {"projectId": PROJECT, "title": "a"})
    assert [c["method"] for c in upstream] == ["GET", "POST"]  # rl 확인 조회 1회
    assert upstream[1]["path"] == f"/rd/{OD}/api/v1/tasks"
    assert upstream[1]["json"]["projectTaskParameters"][0]["taggedProjectKey"] == {"rl": ORL, "domainId": OD, "projectId": PROJECT}

    call(client, "create_task", {"projectId": PROJECT, "title": "b"})
    assert [c["method"] for c in upstream] == ["GET", "POST", "POST"]  # 두 번째부터는 캐시


def test_rl_learned_from_list_projects_skips_lookup(client, upstream):
    call(client, "list_projects", {"spaceId": SPACE})
    call(client, "delete_project", {"projectId": PROJECT})
    assert [c["method"] for c in upstream] == ["GET", "DELETE"]
    assert upstream[-1]["path"] == f"/rl/{ORL}/api/v1/projects/{PROJECT}"


def test_explicit_values_win(client, upstream):
    call(client, "create_task", {"projectId": PROJECT, "title": "a", "domainId": "42", "rl": "7"})
    assert len(upstream) == 1
    assert upstream[0]["path"] == "/rd/42/api/v1/tasks"
    assert upstream[0]["json"]["projectTaskParameters"][0]["taggedProjectKey"]["rl"] == "7"


def test_rl_lookup_failure_falls_back_to_default(client, monkeypatch):
    calls = []

    def handler(req):
        calls.append(req.url.path)
        if req.method == "GET":
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json={"ok": True})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    call(client, "delete_project", {"projectId": PROJECT})
    assert calls[-1] == f"/rl/{I}/api/v1/projects/{PROJECT}"


def test_rest_routes_use_dynamic_values(client, upstream):
    h = {"X-Naverworks-Cookie": USER}
    assert client.get(f"/api/v1/tasks/{TASK}", headers=h).status_code == 200
    assert upstream[-1]["path"] == f"/rd/{OD}/api/v1/tasks/{TASK}"
    r = client.post("/api/v1/tasks", json={"projectId": PROJECT, "title": "t"}, headers=h)
    assert r.status_code == 200
    assert upstream[-1]["json"]["projectTaskParameters"][0]["taggedProjectKey"] == {"rl": ORL, "domainId": OD, "projectId": PROJECT}


def test_tool_schemas_have_no_hardcoded_org_defaults(client):
    for t in client.get("/mcp/tools").json()["tools"]:
        props = t["inputSchema"].get("properties", {})
        for key in ("domainId", "instanceCode", "rl"):
            if key in props:
                assert "default" not in props[key], (t["name"], key)
