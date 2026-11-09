import json
import urllib.parse
import httpx
import pytest
from fastapi.testclient import TestClient

from app.core import client as nw_client
from app.core.payloads import build_mail_move_payload
from app.core.ids import resolve_mail_u, clear_mail_u_cache
from app.core.mail import async_move_mail
from app.core.mcp_spec import get_tools_spec, async_execute_tool
from app.main import app

client = TestClient(app)
DUMMY_COOKIE = "WORKS_SES=dummy-session-value-1234567890; WORKS_USER_ID=dummyuser"


@pytest.fixture(autouse=True)
def clean_state():
    clear_mail_u_cache()
    yield
    clear_mail_u_cache()


def test_build_mail_move_payload():
    # 단일 문자열 SN
    payload = build_mail_move_payload(
        u="100000000000000",
        mail_sn_list="c203",
        target_folder_sn=101,
        folder_sn=0,
    )
    assert payload == {
        "u": "100000000000000",
        "mailSNList": "c203",
        "folderSN": "0",
        "emails": "",
        "targetFolderSN": "101",
        "autoMove": "0",
        "folderName": "",
    }

    # 리스트 SN
    payload_list = build_mail_move_payload(
        u="100000000000000",
        mail_sn_list=["c203", "c204", "c205"],
        target_folder_sn="102",
        folder_sn=1,
        emails="test@example.com",
        auto_move=1,
        folder_name="내 메일함",
    )
    assert payload_list == {
        "u": "100000000000000",
        "mailSNList": "c203,c204,c205",
        "folderSN": "1",
        "emails": "test@example.com",
        "targetFolderSN": "102",
        "autoMove": "1",
        "folderName": "내 메일함",
    }


def test_resolve_mail_u():
    clear_mail_u_cache()
    # 1. 명시적 전달
    assert resolve_mail_u("100000000000000") == "100000000000000"

    # 2. 쿠키에서 추출 (WORKS_USER_NO 또는 u 또는 10자리 이상 숫자 WORKS_USER_ID)
    cookie_str = "WORKS_SES=session123; WORKS_USER_NO=999888777; other=1"
    assert resolve_mail_u(None, cookie=cookie_str) == "999888777"

    cookie_numeric_id = "WORKS_SES=session123; WORKS_USER_ID=100000000000000"
    assert resolve_mail_u(None, cookie=cookie_numeric_id) == "100000000000000"


def test_mcp_spec_includes_move_mail():
    tools = get_tools_spec()
    tool_names = [t["name"] for t in tools]
    assert "move_mail" in tool_names

    tool_def = next(t for t in tools if t["name"] == "move_mail")
    schema = tool_def["inputSchema"]
    assert "mailSNList" in schema["properties"]
    assert "targetFolderSN" in schema["properties"]
    assert "folderSN" in schema["properties"]
    assert "u" in schema["properties"]
    assert "mailSNList" in schema["required"]
    assert "targetFolderSN" in schema["required"]


@pytest.mark.anyio
async def test_move_mail_tool_success(monkeypatch):
    recorded_calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_calls.append({
            "url": str(request.url),
            "method": request.method,
            "headers": dict(request.headers),
            "content": request.content.decode("utf-8"),
        })
        return httpx.Response(200, json={"Result": "OK", "code": 0})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    async def fake_get_async_client():
        return mock_client

    monkeypatch.setattr(nw_client, "get_async_client", fake_get_async_client)

    res = await async_execute_tool(
        "move_mail",
        {
            "u": "100000000000000",
            "mailSNList": "c203",
            "folderSN": 0,
            "emails": "",
            "targetFolderSN": 101,
            "autoMove": 0,
            "folderName": "",
        },
        cookie_override=DUMMY_COOKIE,
    )

    assert not res.get("isError")
    content = json.loads(res["content"][0]["text"])
    assert content["success"] is True
    assert content["mailSNList"] == "c203"
    assert content["targetFolderSN"] == "101"

    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    assert call["method"] == "POST"
    assert call["url"] == "https://mail.worksmobile.com/json/select/move"
    assert "application/x-www-form-urlencoded" in call["headers"]["content-type"]
    parsed_form = urllib.parse.parse_qs(call["content"])
    assert parsed_form["u"] == ["100000000000000"]
    assert parsed_form["mailSNList"] == ["c203"]
    assert parsed_form["targetFolderSN"] == ["101"]
    assert parsed_form["folderSN"] == ["0"]


@pytest.mark.anyio
async def test_move_mail_tool_list_sn(monkeypatch):
    recorded_calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_calls.append(urllib.parse.parse_qs(request.content.decode("utf-8")))
        return httpx.Response(200, json={"Result": "OK"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    async def fake_get_async_client():
        return mock_client

    monkeypatch.setattr(nw_client, "get_async_client", fake_get_async_client)

    res = await async_execute_tool(
        "move_mail",
        {
            "u": "100000000000000",
            "mailSNList": ["c203", "c204", "c205"],
            "targetFolderSN": 102,
        },
        cookie_override=DUMMY_COOKIE,
    )

    assert not res.get("isError")
    assert recorded_calls[0]["mailSNList"] == ["c203,c204,c205"]
    assert recorded_calls[0]["targetFolderSN"] == ["102"]
    assert recorded_calls[0]["folderSN"] == ["0"]


@pytest.mark.anyio
async def test_move_mail_tool_u_memory(monkeypatch):
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"Result": "OK"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    async def fake_get_async_client():
        return mock_client

    monkeypatch.setattr(nw_client, "get_async_client", fake_get_async_client)

    # 1. 첫 번째 호출: 명시적 u 전달 -> 기억됨
    res1 = await async_execute_tool(
        "move_mail",
        {"u": "100000000000000", "mailSNList": "c203", "targetFolderSN": 101},
        cookie_override=DUMMY_COOKIE,
    )
    assert not res1.get("isError")

    # 2. 두 번째 호출: u 생략 -> 기억된 u 사용
    res2 = await async_execute_tool(
        "move_mail",
        {"mailSNList": "c204", "targetFolderSN": 102},
        cookie_override=DUMMY_COOKIE,
    )
    assert not res2.get("isError")


@pytest.mark.anyio
async def test_move_mail_tool_missing_u():
    res = await async_execute_tool(
        "move_mail",
        {"mailSNList": "c203", "targetFolderSN": 101},
        cookie_override=DUMMY_COOKIE,
    )
    assert res.get("isError") is True
    content = json.loads(res["content"][0]["text"])
    assert content["error"] == "MAIL_USER_UNKNOWN"


@pytest.mark.anyio
async def test_move_mail_tool_missing_arguments():
    # missing mailSNList
    res1 = await async_execute_tool(
        "move_mail",
        {"targetFolderSN": 101},
        cookie_override=DUMMY_COOKIE,
    )
    assert res1.get("isError") is True

    # missing targetFolderSN
    res2 = await async_execute_tool(
        "move_mail",
        {"mailSNList": "c203"},
        cookie_override=DUMMY_COOKIE,
    )
    assert res2.get("isError") is True


def test_rest_api_mail_move(monkeypatch):
    recorded_calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_calls.append({
            "url": str(request.url),
            "method": request.method,
            "headers": dict(request.headers),
            "content": request.content.decode("utf-8"),
        })
        return httpx.Response(200, json={"Result": "OK"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    async def fake_get_async_client():
        return mock_client

    monkeypatch.setattr(nw_client, "get_async_client", fake_get_async_client)

    headers = {"X-Naverworks-Cookie": DUMMY_COOKIE}
    payload = {
        "u": "100000000000000",
        "mailSNList": "c203",
        "folderSN": 0,
        "targetFolderSN": 101,
        "autoMove": 0,
    }
    response = client.post("/api/v1/mail/move", json=payload, headers=headers)
    assert response.status_code == 200
    assert response.json() == {"Result": "OK"}
    assert len(recorded_calls) == 1
    call = recorded_calls[0]
    assert call["url"] == "https://mail.worksmobile.com/json/select/move"
    parsed_form = urllib.parse.parse_qs(call["content"])
    assert parsed_form["u"] == ["100000000000000"]
    assert parsed_form["mailSNList"] == ["c203"]
    assert parsed_form["targetFolderSN"] == ["101"]


@pytest.mark.anyio
async def test_async_move_mail_helper(monkeypatch):
    recorded_calls = []

    def mock_handler(request: httpx.Request) -> httpx.Response:
        recorded_calls.append(urllib.parse.parse_qs(request.content.decode("utf-8")))
        return httpx.Response(200, json={"result": "OK"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(mock_handler))

    async def fake_get_async_client():
        return mock_client

    monkeypatch.setattr(nw_client, "get_async_client", fake_get_async_client)

    res = await async_move_mail(
        mail_sn_list=["c203", "c204"],
        target_folder_sn=101,
        folder_sn=0,
        u="100000000000000",
        cookie_override=DUMMY_COOKIE,
    )
    assert res["status"] == 200
    assert res["data"] == {"result": "OK"}
    assert recorded_calls[0]["mailSNList"] == ["c203,c204"]
