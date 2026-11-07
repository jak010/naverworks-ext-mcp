"""list_task_comments: GET /rl/{rl}/api/v1/tasks/{taskId}/task-comments

- rl: 명시 값 → 태스크 캐시 → 태스크 상세 조회(rl 또는 소속 프로젝트의 rl) → 서버 기본값
- 응답 경량화(작성자·본문·시간)와 페이지 처리, 알 수 없는 형식은 원본 유지
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import DEFAULT_INSTANCE_CODE as I
from app.core import client as nw_client
from app.main import app

USER = "WORKS_SES=comment-user-0001; WORKS_USER_ID=c"
OD, ORL = "777000111", "99999"
TASK = f"t-{OD}-c07c7ab8-8fea-4252-aa92-4f46381db251"
PROJECT = f"p-{OD}-11111111-2222-3333-4444-555555555555"

COMMENTS = {"taskComments": [
    {"commentId": f"c-{i}", "writer": {"userId": "u-1", "name": "홍길동"},
     "content": {"htmlText": f"<p>댓글 {i} &amp; 확인</p>", "plainText": ""},
     "created": 1762500000000 + i, "modified": None, "mentionedUserIds": [], "reactions": [{"type": "LIKE"}] * 5}
    for i in range(45)
]}


def make_upstream(monkeypatch, task_body=None, comments=COMMENTS, comment_status=200):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        calls.append((req.method, path))
        if path.endswith("/task-comments"):
            return httpx.Response(comment_status, json=comments)
        if "/tasks/" in path:
            return httpx.Response(200, json=task_body or {"task": {"taskId": TASK, "mainProjectId": PROJECT}})
        if "/projects/" in path:
            return httpx.Response(200, json={"project": {"projectId": PROJECT, "rl": ORL}})
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


def call(client, args):
    r = client.post("/mcp/call", json={"name": "list_task_comments", "arguments": args}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200, r.text
    return r.json()


def comment_paths(calls):
    return [p for m, p in calls if p.endswith("/task-comments")]


def test_tool_is_listed(client):
    names = [t["name"] for t in client.get("/mcp/tools").json()["tools"]]
    assert "list_task_comments" in names


def test_rl_from_task_project_then_cached(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    res = call(client, {"taskId": TASK})
    assert res["isError"] is False
    assert comment_paths(calls) == [f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments"]
    assert ("GET", f"/rd/{OD}/api/v1/tasks/{TASK}") in calls  # 태스크 → 프로젝트 → rl

    calls.clear()
    call(client, {"taskId": TASK})
    assert calls == [("GET", f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments")]  # 두 번째는 캐시


def test_rl_from_task_response_rl_field(client, monkeypatch):
    calls = make_upstream(monkeypatch, task_body={"task": {"taskId": TASK, "rl": "55555"}})
    call(client, {"taskId": TASK})
    assert comment_paths(calls) == [f"/rl/55555/api/v1/tasks/{TASK}/task-comments"]


def test_rl_learned_from_list_tasks_skips_lookup(client, monkeypatch):
    make_upstream(monkeypatch)
    from app.core.ids import remember_rl
    remember_rl({"projectTasks": [{"taskId": TASK, "rl": "44444"}]})
    calls = make_upstream(monkeypatch)
    call(client, {"taskId": TASK})
    assert calls == [("GET", f"/rl/44444/api/v1/tasks/{TASK}/task-comments")]


def test_explicit_rl_wins(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    call(client, {"taskId": TASK, "rl": "24101"})
    assert calls == [("GET", f"/rl/24101/api/v1/tasks/{TASK}/task-comments")]


def test_lookup_failure_falls_back_to_default_rl(client, monkeypatch):
    calls = make_upstream(monkeypatch, task_body={"task": {"taskId": TASK}})
    call(client, {"taskId": TASK})
    assert comment_paths(calls) == [f"/rl/{I}/api/v1/tasks/{TASK}/task-comments"]


def test_comments_are_slim_and_paginated(client, monkeypatch):
    make_upstream(monkeypatch)
    data = json.loads(call(client, {"taskId": TASK, "rl": ORL})["content"][0]["text"])
    assert data["total"] == 45 and data["returned"] == 30 and data["hasMore"] is True
    first = data["comments"][0]
    assert first == {"commentId": "c-0", "author": "홍길동", "text": "댓글 0 & 확인", "created": 1762500000000}

    data = json.loads(call(client, {"taskId": TASK, "rl": ORL, "offset": 30})["content"][0]["text"])
    assert data["returned"] == 15 and data["hasMore"] is False


@pytest.mark.parametrize("body", [
    [{"id": "c-1", "authorName": "김", "comment": "평문 댓글"}],                          # 배열 그대로
    {"result": [{"taskCommentId": "c-1", "userName": "김", "body": "<b>평문</b> 댓글"}]},  # 알 수 없는 래핑 키
])
def test_other_response_shapes(client, monkeypatch, body):
    make_upstream(monkeypatch, comments=body)
    data = json.loads(call(client, {"taskId": TASK, "rl": ORL})["content"][0]["text"])
    c = data["comments"][0]
    assert c["commentId"] == "c-1" and c["author"] == "김" and "댓글" in c["text"] and "<" not in c["text"]


def test_unknown_shape_returns_pruned_original(client, monkeypatch):
    make_upstream(monkeypatch, comments={"count": 0, "next": None})
    data = json.loads(call(client, {"taskId": TASK, "rl": ORL})["content"][0]["text"])
    assert data == {"count": 0}


def test_error_is_reported(client, monkeypatch):
    make_upstream(monkeypatch, comments={"code": "NOT_FOUND"}, comment_status=404)
    res = call(client, {"taskId": TASK, "rl": ORL})
    assert res["isError"] is True and json.loads(res["content"][0]["text"])["status"] == 404


def test_rest_route(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    r = client.get(f"/api/v1/tasks/{TASK}/comments", params={"rl": ORL}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200 and r.json() == COMMENTS
    assert comment_paths(calls) == [f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments"]


# ---------------------------------------------------------------------------
# create_task_comment: POST /rl/{rl}/api/v1/tasks/{taskId}/task-comments
# ---------------------------------------------------------------------------

def post_calls(calls):
    return [p for m, p in calls if m == "POST"]


@pytest.fixture
def post_upstream(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content) if req.content else None
        calls.append((req.method, req.url.path, body))
        if req.method == "POST":
            return httpx.Response(200, json={"taskCommentId": "tc-1", "writer": {"name": "홍길동"}, "content": body["content"],
                                             "created": 1762500000000, "parentTaskCommentId": body["parentTaskCommentId"],
                                             "reactions": [], "files": []})
        if path_is_task(req.url.path):
            return httpx.Response(200, json={"task": {"taskId": TASK, "rl": ORL}})
        return httpx.Response(200, json={"ok": True})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    return calls


def path_is_task(path):
    return "/tasks/" in path and not path.endswith("/task-comments")


def create(client, args):
    r = client.post("/mcp/call", json={"name": "create_task_comment", "arguments": args}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200, r.text
    return r.json()


def test_create_comment_sends_exact_payload(client, post_upstream):
    res = create(client, {"taskId": TASK, "htmlText": "댓글 추가 테스트"})
    assert res["isError"] is False
    method, path, body = post_upstream[-1]
    assert (method, path) == ("POST", f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments")
    assert body == {"parentTaskCommentId": None, "content": {"htmlText": "댓글 추가 테스트", "inlineImages": [], "mentionedUserIds": []}, "files": []}
    data = json.loads(res["content"][0]["text"])
    assert data == {"created": True, "taskId": TASK, "comment": {"commentId": "tc-1", "author": "홍길동", "text": "댓글 추가 테스트", "created": 1762500000000}}


def test_reply_sets_parent(client, post_upstream):
    create(client, {"taskId": TASK, "htmlText": "답글", "parentTaskCommentId": "tc-1", "rl": "24101"})
    method, path, body = post_upstream[-1]
    assert path == f"/rl/24101/api/v1/tasks/{TASK}/task-comments" and body["parentTaskCommentId"] == "tc-1"
    assert len(post_upstream) == 1  # rl 명시 → 조회 없음


def test_empty_comment_rejected_without_request(client, post_upstream):
    res = create(client, {"taskId": TASK, "htmlText": "   "})
    assert res["isError"] is True and post_upstream == []


def test_create_invalidates_comment_cache(client, post_upstream):
    from app.core import mcp_spec
    mcp_spec.set_cached_result("x", 1)
    create(client, {"taskId": TASK, "htmlText": "a", "rl": ORL})
    assert mcp_spec.get_cached_result("x") is None


def test_create_comment_rest_route(client, post_upstream):
    r = client.post(f"/api/v1/tasks/{TASK}/comments", json={"htmlText": "REST 댓글", "rl": ORL}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200 and r.json()["taskCommentId"] == "tc-1"
    assert post_upstream[-1][2]["content"]["htmlText"] == "REST 댓글"
    assert client.post(f"/api/v1/tasks/{TASK}/comments", json={"htmlText": ""}, headers={"X-Naverworks-Cookie": USER}).status_code == 422


# ---------------------------------------------------------------------------
# delete_task_comment: DELETE /rl/{rl}/api/v1/tasks/{taskId}/task-comments/{taskCommentId}
# ---------------------------------------------------------------------------

COMMENT = "tc-e7eead91-3ee9-495a-b70a-a08867ccdedf"


def delete(client, args):
    r = client.post("/mcp/call", json={"name": "delete_task_comment", "arguments": args}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("status", [200, 204])
def test_delete_comment(client, monkeypatch, status):
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        if req.method == "DELETE":
            return httpx.Response(status)
        return httpx.Response(200, json={"task": {"taskId": TASK, "rl": ORL}})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    res = delete(client, {"taskId": TASK, "taskCommentId": COMMENT})
    assert res["isError"] is False
    assert json.loads(res["content"][0]["text"]) == {"deleted": True, "taskId": TASK, "taskCommentId": COMMENT}
    assert calls[-1] == ("DELETE", f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments/{COMMENT}")


def test_delete_comment_error_and_invalid_id(client, monkeypatch):
    calls = make_upstream(monkeypatch)
    for bad in ("", "  ", "tc-1/../x"):
        assert delete(client, {"taskId": TASK, "taskCommentId": bad, "rl": ORL})["isError"] is True
    assert calls == []  # 잘못된 ID는 요청하지 않음

    def handler(req):
        return httpx.Response(403, json={"code": "FORBIDDEN"})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    res = delete(client, {"taskId": TASK, "taskCommentId": COMMENT, "rl": ORL})
    assert res["isError"] is True and json.loads(res["content"][0]["text"])["status"] == 403


def test_delete_comment_rest_route(client, monkeypatch):
    calls = []

    def handler(req):
        calls.append((req.method, req.url.path))
        return httpx.Response(200, json={"ok": True})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    r = client.delete(f"/api/v1/tasks/{TASK}/comments/{COMMENT}", params={"rl": ORL}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200
    assert calls == [("DELETE", f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments/{COMMENT}")]


# ---------------------------------------------------------------------------
# update_task_comment: POST .../task-comments/{taskCommentId}/modify-task-comment-content
# ---------------------------------------------------------------------------

EDIT_ID = "tc-318e546f-8e16-49ec-ba36-8437389455fe"


@pytest.fixture
def edit_upstream(monkeypatch):
    calls = []

    def handler(req):
        body = json.loads(req.content) if req.content else None
        calls.append((req.method, req.url.path, body))
        if req.method == "POST":
            return httpx.Response(200)
        return httpx.Response(200, json={"task": {"taskId": TASK, "rl": ORL}})

    mock = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    async def fake():
        return mock

    monkeypatch.setattr(nw_client, "get_async_client", fake)
    return calls


def update(client, args):
    r = client.post("/mcp/call", json={"name": "update_task_comment", "arguments": args}, headers={"X-Naverworks-Cookie": USER})
    assert r.status_code == 200, r.text
    return r.json()


def test_update_comment_sends_exact_payload(client, edit_upstream):
    res = update(client, {"taskId": TASK, "taskCommentId": EDIT_ID, "htmlText": "리포트 기능 참고 #2"})
    assert res["isError"] is False
    method, path, body = edit_upstream[-1]
    assert (method, path) == ("POST", f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments/{EDIT_ID}/modify-task-comment-content")
    assert body == {"content": {"htmlText": "리포트 기능 참고 #2", "inlineImages": [], "mentionedUserIds": []}}
    assert json.loads(res["content"][0]["text"]) == {"updated": True, "taskId": TASK, "taskCommentId": EDIT_ID, "text": "리포트 기능 참고 #2"}


def test_update_comment_rejects_bad_input_without_request(client, edit_upstream):
    assert update(client, {"taskId": TASK, "taskCommentId": EDIT_ID, "htmlText": " "})["isError"] is True
    assert update(client, {"taskId": TASK, "taskCommentId": "tc-1/x", "htmlText": "a"})["isError"] is True
    assert edit_upstream == []


def test_update_comment_rest_route(client, edit_upstream):
    h = {"X-Naverworks-Cookie": USER}
    r = client.put(f"/api/v1/tasks/{TASK}/comments/{EDIT_ID}", json={"htmlText": "REST 수정", "rl": ORL}, headers=h)
    assert r.status_code == 200
    assert edit_upstream[-1][1] == f"/rl/{ORL}/api/v1/tasks/{TASK}/task-comments/{EDIT_ID}/modify-task-comment-content"
    assert edit_upstream[-1][2]["content"]["htmlText"] == "REST 수정"
    assert client.put(f"/api/v1/tasks/{TASK}/comments/{EDIT_ID}", json={"htmlText": ""}, headers=h).status_code == 422
