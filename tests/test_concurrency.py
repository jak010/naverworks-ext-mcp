import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.anyio
async def test_concurrent_api_requests():
    """30개의 동시 요청이 들어와도 안전하고 빠르게 응답하는지 검증합니다."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 30개의 동시 요청 생성
        tasks = [client.get("/health") for _ in range(30)]
        responses = await asyncio.gather(*tasks)

        assert len(responses) == 30
        for r in responses:
            assert r.status_code == 200
            assert r.json() == {"status": "ok"}
            assert "X-Request-ID" in r.headers
            assert "X-Process-Time" in r.headers


@pytest.mark.anyio
async def test_concurrent_mcp_tools_and_rpc():
    """다수의 MCP 도구 목록 조회 및 RPC 호출이 동시에 들어와도 교착상태 없이 정상 처리되는지 검증합니다."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # tools 목록 조회 15개 + RPC ping 15개 동시 실행
        tasks = []
        for i in range(15):
            tasks.append(client.get("/mcp/tools"))
            tasks.append(client.post("/mcp/rpc", json={"jsonrpc": "2.0", "id": i, "method": "ping"}))

        responses = await asyncio.gather(*tasks)
        assert len(responses) == 30
        for r in responses:
            assert r.status_code == 200


@pytest.mark.anyio
async def test_concurrent_cookie_access():
    """다수의 스레드/코루틴이 동시에 쿠키 헤더를 요청해도 안전하게 캐시에서 반환하는지 검증합니다."""
    from app.core.cookie import get_cookie_header

    loop = asyncio.get_running_loop()
    # 20개의 스레드 풀에서 동시 쿠키 조회
    tasks = [loop.run_in_executor(None, get_cookie_header) for _ in range(20)]
    results = await asyncio.gather(*tasks)

    assert len(results) == 20
    first_result = results[0]
    for res in results:
        assert res == first_result


@pytest.mark.anyio
async def test_concurrent_mcp_sessions():
    """여러 MCP 클라이언트가 동시에 세션을 등록하고 메시지를 주고받아도 격리되어 처리되는지 검증합니다."""
    from app.api.mcp import session_manager

    sids = [f"session-{i}" for i in range(10)]
    # 10개 동시 등록
    queues = await asyncio.gather(*(session_manager.register(sid) for sid in sids))
    assert await session_manager.active_session_count() >= 10

    # 각 큐에 메시지 독립 전송 및 확인
    for i, q in enumerate(queues):
        await q.put(f"msg-{i}")
        msg = await q.get()
        assert msg == f"msg-{i}"

    # 10개 동시 해제
    await asyncio.gather(*(session_manager.unregister(sid) for sid in sids))


@pytest.mark.anyio
async def test_user_cookie_override(tmp_path, local_mode):
    """사용자가 MCP 헤더나 쿼리 파라미터로 쿠키를 전달했을 때 해당 쿠키가 반영되는지 검증합니다.
    (파일 경로 입력(3, 4번)은 local 모드에서만 허용 — multi_user 차단은 test_multi_user.py에서 검증)"""
    from app.api.mcp import extract_cookie_override
    from starlette.requests import Request

    cookie_file = tmp_path / "user_cookies.txt"
    cookie_file.write_text(
        "# Netscape HTTP Cookie File\n"
        ".worksmobile.com\tTRUE\t/\tTRUE\t2147483647\tWORKS_SES\tfile-session-0123456789\n",
        encoding="utf-8",
    )

    # 1. X-Naverworks-Cookie 헤더 전달
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/sse",
        "headers": [(b"x-naverworks-cookie", b"USER_TOKEN=custom123; WORKS_USER=test")],
        "query_string": b"",
    }
    req = Request(scope)
    assert extract_cookie_override(req) == "USER_TOKEN=custom123; WORKS_USER=test"

    # 2. URL Query 파라미터 전달
    scope_query = {
        "type": "http",
        "method": "GET",
        "path": "/sse",
        "headers": [],
        "query_string": b"cookie=USER_TOKEN%3Dquery123",
    }
    req_query = Request(scope_query)
    assert extract_cookie_override(req_query) == "USER_TOKEN=query123"

    # 3. X-Naverworks-Cookie-Path 파일 경로 헤더 전달
    scope_path = {
        "type": "http",
        "method": "GET",
        "path": "/sse",
        "headers": [(b"x-naverworks-cookie-path", str(cookie_file).encode())],
        "query_string": b"",
    }
    req_path = Request(scope_path)
    res_path = extract_cookie_override(req_path)
    assert res_path == "WORKS_SES=file-session-0123456789"

    # 4. ?cookie_path= URL 쿼리 파라미터 전달
    scope_query_path = {
        "type": "http",
        "method": "GET",
        "path": "/sse",
        "headers": [],
        "query_string": f"cookie_path={cookie_file}".encode(),
    }
    req_query_path = Request(scope_query_path)
    res_query_path = extract_cookie_override(req_query_path)
    assert res_query_path == "WORKS_SES=file-session-0123456789"


