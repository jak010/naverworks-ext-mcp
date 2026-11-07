"""LLM 토큰 절감: 간결한 JSON, 빈 값 생략, list_tasks 페이지·필터, 생성 결과·오류 축약, HTML 본문 텍스트화"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import client as nw_client
from app.main import app

USER = "WORKS_SES=size-user-session-0001; WORKS_USER_ID=size"
P = "p-300098158-11111111-2222-3333-4444-555555555555"


def _task(i, status="OPEN"):
    return {"taskId": f"t-300098158-{i:04d}", "title": f"태스크 {i}", "status": {"taskStatusType": status, "lastModified": 1},
            "content": {"htmlText": f"<p>본문 {i}</p>", "plainText": f"본문 {i} " * 30}, "parentTaskId": None, "due": None,
            "assigneeIds": ["u-1"], "rl": "24101", "domainId": "300098158"}


@pytest.fixture
def upstream(monkeypatch):
    calls = []
    state = {"error": None}

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if state["error"]:
            return state["error"]
        path = req.url.path
        if req.method == "GET" and path.endswith("/tasks"):
            tasks = [_task(i, "DONE" if i % 4 == 0 else "OPEN") for i in range(120)]
            return httpx.Response(200, json={"projectTasks": tasks, "relatedUserIds": ["u-1"] * 50})
        if req.method == "GET" and "/tasks/" in path:
            return httpx.Response(200, json={"task": {"taskId": "t-300098158-x", "title": "상세", "status": {"taskStatusType": "OPEN"},
                                                      "content": {"htmlText": "<p>첫 줄 &amp; 둘째</p><ul><li>항목1</li><li>항목2</li></ul>", "plainText": ""}}})
        if req.method == "POST" and path.endswith("/projects"):
            return httpx.Response(200, json={"projectId": P, "projectName": "새 프로젝트", "rl": "24101",
                                             "projectViews": [{"viewId": f"v{i}", "config": "x" * 200} for i in range(20)],
                                             "customFields": [{"fieldId": f"f{i}", "options": list(range(50))} for i in range(10)]})
        if req.method == "POST" and path.endswith("/tasks"):
            return httpx.Response(200, json={"taskId": "t-300098158-new", "title": "새 태스크", "status": {"taskStatusType": "OPEN"},
                                             "mainProjectId": P, "content": {"htmlText": "<p>" + "긴 본문 " * 500 + "</p>"},
                                             "project": {"projectViews": ["x" * 300] * 10}})
        return httpx.Response(200, json={"ok": True})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    return {"calls": calls, "state": state}


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def call(client, name, args):
    r = client.post("/mcp/call", json={"name": name, "arguments": args}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200, r.text
    body = r.json()
    return body, body["content"][0]["text"]


def test_list_tasks_paginates_and_hides_preview_by_default(client, upstream):
    body, text = call(client, "list_tasks", {"projectId": P})
    data = json.loads(text)
    assert data["total"] == 120 and data["returned"] == 50 and data["hasMore"] is True
    assert "contentPreview" not in data["tasks"][0]
    assert "\n" not in text and ": " not in text  # 간결한 JSON
    assert "parentTaskId" not in data["tasks"][0]  # null 생략

    _, text2 = call(client, "list_tasks", {"projectId": P, "offset": 100, "limit": 50})
    page2 = json.loads(text2)
    assert page2["returned"] == 20 and page2["hasMore"] is False
    assert len(upstream["calls"]) == 1  # 두 번째 페이지는 캐시에서


def test_list_tasks_status_filter_and_preview(client, upstream):
    _, text = call(client, "list_tasks", {"projectId": P, "status": "done", "includePreview": True, "limit": 500})
    data = json.loads(text)
    assert data["total"] == 30 and all(t["status"] == "DONE" for t in data["tasks"])
    assert len(data["tasks"][0]["contentPreview"]) <= 83


def test_get_task_converts_html_to_text(client, upstream):
    _, text = call(client, "get_task", {"taskId": "t-300098158-x"})
    content = json.loads(text)["content"]
    assert "<" not in content and "첫 줄 & 둘째" in content and "항목1\n항목2" in content


def test_create_results_are_slim(client, upstream):
    _, text = call(client, "create_project", {"spaceId": "s-300098158-1", "projectName": "새 프로젝트"})
    assert json.loads(text) == {"projectId": P, "projectName": "새 프로젝트"}
    _, text = call(client, "create_task", {"projectId": P, "title": "새 태스크", "rl": "24101"})
    data = json.loads(text)
    assert data["taskId"] == "t-300098158-new" and data["projectId"] == P and "content" not in data
    assert len(text) < 300


def test_upstream_error_body_is_truncated(client, upstream):
    upstream["state"]["error"] = httpx.Response(500, text="<html><body>" + "<p>서버 오류</p>" * 2000 + "</body></html>")
    body, text = call(client, "get_task", {"taskId": "t-300098158-x"})
    assert body["isError"] is True
    data = json.loads(text)
    assert data["status"] == 500 and "<" not in data["error"] and len(data["error"]) <= 510
