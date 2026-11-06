"""MCP SSE 전송 규격 검증 (2024-11-05 HTTP+SSE transport)

- POST /messages 는 202 Accepted 만 반환하고 본문에 JSON-RPC 응답을 담지 않는다.
- JSON-RPC 응답은 SSE 스트림(event: message)으로 정확히 한 번 전달된다.
- 알림(id 없음)에는 응답을 보내지 않는다.
- SSE 큐가 가득 차 응답을 전달할 수 없으면 조용히 버리지 않고 503으로 실패를 알린다.
"""

import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient

from app.api import mcp as mcp_api
from app.api.mcp import session_manager, MCPSession
from app.main import app

USER = "WORKS_SES=sse-user-session-0000000001; WORKS_USER_ID=sse-user"


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _session(maxsize=100, cookie=None):
    sid = f"t-{os.urandom(6).hex()}"
    session_manager._sessions[sid] = MCPSession(sid, asyncio.Queue(maxsize=maxsize), cookie)
    return sid


def _drain(sid):
    q = session_manager._sessions[sid].queue
    out = []
    while not q.empty():
        out.append(json.loads(q.get_nowait()))
    return out


def test_post_returns_202_without_jsonrpc_body(client):
    sid = _session()
    try:
        r = client.post(f"/messages?session_id={sid}", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert r.status_code == 202
        assert r.text == "Accepted"
        assert _drain(sid) == [{"jsonrpc": "2.0", "id": 1, "result": {}}]
    finally:
        session_manager._sessions.pop(sid, None)


@pytest.mark.parametrize("method", ["initialize", "tools/list", "ping", "unknown/method"])
def test_each_request_produces_exactly_one_sse_response(client, method):
    sid = _session()
    try:
        r = client.post(f"/messages?session_id={sid}", json={"jsonrpc": "2.0", "id": 42, "method": method, "params": {}})
        assert r.status_code == 202
        out = _drain(sid)
        assert len(out) == 1 and out[0]["id"] == 42
        if method == "unknown/method":
            assert out[0]["error"]["code"] == -32601
    finally:
        session_manager._sessions.pop(sid, None)


@pytest.mark.parametrize("method", ["notifications/initialized", "notifications/cancelled"])
def test_notifications_get_no_response(client, method):
    sid = _session()
    try:
        r = client.post(f"/messages?session_id={sid}", json={"jsonrpc": "2.0", "method": method, "params": {}})
        assert r.status_code == 202
        assert _drain(sid) == []
    finally:
        session_manager._sessions.pop(sid, None)


def test_full_queue_reports_503_instead_of_dropping(client, monkeypatch):
    monkeypatch.setattr(mcp_api, "SSE_ENQUEUE_TIMEOUT", 0.05)
    sid = _session(maxsize=1)
    try:
        session_manager._sessions[sid].queue.put_nowait("unconsumed")
        r = client.post(f"/messages?session_id={sid}", json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert r.status_code == 503
    finally:
        session_manager._sessions.pop(sid, None)


def test_end_to_end_sse_stream_with_user_cookie(client, mock_upstream):
    """실제 SSE 스트림: 핸드셰이크(쿠키) → initialize → tools/list → tools/call 응답을 스트림에서 수신"""
    with client.stream("GET", "/sse", headers={"X-Naverworks-Cookie": USER}) as stream:
        lines = stream.iter_lines()

        def next_event():
            event = None
            for line in lines:
                if line.startswith("event:"):
                    event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    return event, line.split(":", 1)[1].strip()

        event, endpoint = next_event()
        assert event == "endpoint" and endpoint.startswith("/messages?session_id=")

        def send(req):
            r = client.post(endpoint, json=req)
            assert r.status_code == 202
            ev, data = next_event()
            assert ev == "message"
            return json.loads(data)

        init = send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})
        assert init["result"]["serverInfo"]["name"]
        assert client.post(endpoint, json={"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202

        tools = send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert "list_spaces" in [t["name"] for t in tools["result"]["tools"]]

        call = send({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_spaces", "arguments": {}}})
        assert call["id"] == 3 and call["result"]["isError"] is False
        assert json.loads(call["result"]["content"][0]["text"])[0]["spaceName"] == f"owner:{USER}"

    assert [c["cookie"] for c in mock_upstream] == [USER]
