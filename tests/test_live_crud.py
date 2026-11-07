"""실제 네이버웍스 대상 CRUD 통합 테스트 (opt-in)

기본적으로 건너뜁니다. 실제 데이터를 생성/삭제하므로 명시적으로 켜야 합니다:

    NAVERWORKS_LIVE_COOKIE_PATH=~/.config/naverworks/proj_cookies.txt pytest tests/test_live_crud.py -v

- 서버는 multi_user 모드(익명 다중 사용자 서비스)로 동작하며, 쿠키는 사용자 요청 헤더로만 전달합니다.
- MCP SSE 전송(핸드셰이크 → initialize → tools/call) 과 REST API 양쪽을 검증합니다.
- 생성한 리소스 이름에는 '[MCP-TEST] <시각>' 접두사가 붙고, 실패하더라도 finally에서 모두 삭제합니다.
"""

import json
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_DOMAIN_ID as D, DEFAULT_INSTANCE_CODE as I
from app.core.client import api_request
from app.core.cookie import read_cookie_file
from app.main import app

LIVE_COOKIE_PATH = os.getenv("NAVERWORKS_LIVE_COOKIE_PATH")
pytestmark = pytest.mark.skipif(not LIVE_COOKIE_PATH, reason="NAVERWORKS_LIVE_COOKIE_PATH 미설정 (실제 네이버웍스 쓰기 테스트)")

TAG = f"[MCP-TEST] {time.strftime('%Y%m%d-%H%M%S')}"


@pytest.fixture(scope="module")
def user_cookie():
    ck = read_cookie_file(LIVE_COOKIE_PATH)
    assert ck, f"쿠키 파일을 읽을 수 없습니다: {LIVE_COOKIE_PATH}"
    return ck


class SseSession:
    """실제 SSE 스트림을 통해 JSON-RPC 요청/응답을 주고받는 최소 MCP 클라이언트"""

    def __init__(self, client, stream):
        self.client = client
        self.lines = stream.iter_lines()
        self.req_id = 0
        event, self.endpoint = self._next_event()
        assert event == "endpoint"

    def _next_event(self):
        event = None
        for line in self.lines:
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                return event, line.split(":", 1)[1].strip()
        raise AssertionError("SSE 스트림이 종료됨")

    def request(self, method, params=None):
        self.req_id += 1
        r = self.client.post(self.endpoint, json={"jsonrpc": "2.0", "id": self.req_id, "method": method, "params": params or {}})
        assert r.status_code == 202, r.text
        event, data = self._next_event()
        assert event == "message"
        msg = json.loads(data)
        assert msg["id"] == self.req_id
        return msg

    def tool(self, name, args=None, expect_error=False):
        result = self.request("tools/call", {"name": name, "arguments": args or {}})["result"]
        text = result["content"][0]["text"]
        try:
            payload = json.loads(text)
        except ValueError:
            payload = text
        assert result["isError"] is expect_error, f"{name}: {payload}"
        return payload


def _cleanup(cookie, created):
    """앱과 무관한 직접 호출로 생성 리소스 정리 (역순)"""
    for tid in reversed(created["tasks"]):
        api_request("DELETE", f"/rd/{D}/api/v1/tasks/{tid}", cookie_override=cookie)
    for pid in created["projects"]:
        api_request("DELETE", f"/rl/{I}/api/v1/projects/{pid}", cookie_override=cookie)
    for sid in created["spaces"]:
        api_request("DELETE", f"/rd/{D}/api/v1/spaces/{sid}", cookie_override=cookie)
    leftovers = [s for s in (api_request("GET", f"/rd/{D}/api/v1/spaces", cookie_override=cookie).get("data") or [])
                 if s.get("spaceName") == TAG]
    assert leftovers == [], f"정리되지 않은 테스트 스페이스: {leftovers}"


def test_live_mcp_sse_crud_lifecycle(user_cookie):
    created = {"spaces": [], "projects": [], "tasks": []}
    try:
        with TestClient(app) as client:
            # 쿠키 없는 익명 사용자는 차단
            with client.stream("GET", "/sse") as anon_stream:
                anon = SseSession(client, anon_stream)
                assert anon.tool("list_spaces", expect_error=True)["error"] == "UNAUTHORIZED"

            with client.stream("GET", "/sse", headers={"X-Naverworks-Cookie": user_cookie}) as stream:
                s = SseSession(client, stream)
                init = s.request("initialize", {"protocolVersion": "2024-11-05"})
                assert init["result"]["capabilities"]["tools"] is not None
                tool_names = [t["name"] for t in s.request("tools/list")["result"]["tools"]]
                assert "login_naverworks" in tool_names

                auth = s.tool("get_auth_status")
                assert auth["isAuthenticated"] is True

                # --- Space
                space = s.tool("create_space", {"spaceName": TAG})
                space_id = space["spaceId"]
                created["spaces"].append(space_id)
                assert s.tool("get_space", {"spaceId": space_id})["spaceName"] == TAG
                assert space_id in [x["spaceId"] for x in s.tool("list_spaces")]

                # --- Project
                project = s.tool("create_project", {"spaceId": space_id, "projectName": TAG})
                project_id = project["projectId"]
                created["projects"].append(project_id)
                assert s.tool("get_project", {"projectId": project_id})["projectName"] == TAG
                assert project_id in [x["projectId"] for x in s.tool("list_projects", {"spaceId": space_id})]

                # --- Task + 하위 태스크
                task = s.tool("create_task", {"projectId": project_id, "title": f"{TAG} 태스크", "htmlText": "<p>초기 본문</p>"})
                task_id = task["taskId"]
                created["tasks"].append(task_id)
                sub = s.tool("create_task", {"projectId": project_id, "title": f"{TAG} 하위", "parentTaskId": task_id})
                sub_id = sub["taskId"]
                created["tasks"].append(sub_id)

                listed = {t["taskId"]: t for t in s.tool("list_tasks", {"projectId": project_id})["tasks"]}
                assert task_id in listed and sub_id in listed
                assert listed[sub_id]["parentTaskId"] == task_id

                got = s.tool("get_task", {"taskId": task_id})
                assert got["title"] == f"{TAG} 태스크"

                # --- Update
                s.tool("update_task_content", {"taskId": task_id, "htmlText": "<p>MCP 수정 확인</p>"})
                assert "MCP 수정 확인" in s.tool("get_task", {"taskId": task_id})["content"]

                # --- Delete (역순)
                s.tool("delete_task", {"taskId": sub_id})
                created["tasks"].remove(sub_id)
                s.tool("delete_task", {"taskId": task_id})
                created["tasks"].remove(task_id)
                remaining = [t["taskId"] for t in s.tool("list_tasks", {"projectId": project_id})["tasks"]]
                assert task_id not in remaining and sub_id not in remaining

                s.tool("delete_project", {"projectId": project_id})
                created["projects"].remove(project_id)
                s.tool("delete_space", {"spaceId": space_id})
                created["spaces"].remove(space_id)
                assert space_id not in [x["spaceId"] for x in s.tool("list_spaces")]
    finally:
        _cleanup(user_cookie, created)


def test_live_rest_crud_lifecycle(user_cookie):
    created = {"spaces": [], "projects": [], "tasks": []}
    h = {"X-Naverworks-Cookie": user_cookie}
    try:
        with TestClient(app) as c:
            assert c.get("/api/v1/spaces").status_code == 401
            assert c.get("/api/v1/spaces", headers={"X-Naverworks-Cookie": "WORKS_SES=forged-invalid-session-0000"}).status_code >= 400

            r = c.post("/api/v1/spaces", json={"spaceName": TAG}, headers=h)
            assert r.status_code == 200, r.text
            space_id = r.json()["spaceId"]
            created["spaces"].append(space_id)

            r = c.post("/api/v1/projects", json={"spaceId": space_id, "projectName": TAG}, headers=h)
            assert r.status_code == 200, r.text
            project_id = r.json()["projectId"]
            created["projects"].append(project_id)
            assert c.get(f"/api/v1/projects/{project_id}", headers=h).status_code == 200

            r = c.post("/api/v1/tasks", json={"projectId": project_id, "title": f"{TAG} REST"}, headers=h)
            assert r.status_code == 200, r.text
            task_id = r.json()["taskId"]
            created["tasks"].append(task_id)

            assert c.put(f"/api/v1/tasks/{task_id}/content", json={"htmlText": "<p>REST 수정 확인</p>"}, headers=h).status_code == 200
            assert "REST 수정 확인" in json.dumps(c.get(f"/api/v1/tasks/{task_id}", headers=h).json(), ensure_ascii=False)

            assert c.delete(f"/api/v1/tasks/{task_id}", headers=h).status_code == 200
            created["tasks"].remove(task_id)
            assert c.delete(f"/api/v1/projects/{project_id}", headers=h).status_code == 200
            created["projects"].remove(project_id)
            assert c.delete(f"/api/v1/spaces/{space_id}", headers=h).status_code == 200
            created["spaces"].remove(space_id)
    finally:
        _cleanup(user_cookie, created)
