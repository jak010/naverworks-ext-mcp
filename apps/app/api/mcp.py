import json
import uuid
import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from app.core.mcp_spec import get_tools_spec, async_execute_tool
from app.core.cookie import read_user_cookie_path
from app.core.auth_context import set_current_user_cookie
from app.schemas.mcp import MCPJsonRpcRequest
from app.api.deps import extract_cookie_override
from app.api.oauth import unauthorized_response
from app.core.cookie import get_cookie_header
from app import config

logger = logging.getLogger("mcp")

SSE_ENQUEUE_TIMEOUT = 5.0  # SSE 큐가 가득 찼을 때 응답 적재를 기다리는 최대 시간(초)
router = APIRouter(tags=["MCP"])


@dataclass
class MCPSession:
    session_id: str
    queue: asyncio.Queue
    cookie_override: Optional[str] = None


class MCPSessionManager:
    """동시 다발적 MCP 연결에 대해 스레드/비동기 안전성을 보장하고 사용자별 쿠키를 유지하는 세션 관리자"""

    def __init__(self):
        self._sessions: Dict[str, MCPSession] = {}
        self._lock = asyncio.Lock()

    async def register(self, session_id: str, cookie_override: Optional[str] = None) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        async with self._lock:
            self._sessions[session_id] = MCPSession(
                session_id=session_id,
                queue=queue,
                cookie_override=cookie_override
            )
        return queue

    async def unregister(self, session_id: str) -> None:
        async with self._lock:
            self._sessions.pop(session_id, None)

    async def get_session(self, session_id: str) -> Optional[MCPSession]:
        async with self._lock:
            return self._sessions.get(session_id)

    async def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        async with self._lock:
            sess = self._sessions.get(session_id)
            return sess.queue if sess else None

    async def is_active(self, session_id: str) -> bool:
        async with self._lock:
            return session_id in self._sessions

    async def active_session_count(self) -> int:
        async with self._lock:
            return len(self._sessions)


session_manager = MCPSessionManager()


def _is_upstream_unauthorized(result: Dict[str, Any]) -> bool:
    """도구 실행 결과가 네이버웍스 401(세션 만료)인지 확인"""
    if not result.get("isError"):
        return False
    try:
        payload = json.loads(result["content"][0]["text"])
    except (KeyError, IndexError, TypeError, ValueError):
        return False
    return isinstance(payload, dict) and payload.get("status") == 401


@router.get("/mcp/tools", summary="MCP 지원 도구 목록 조회")
async def list_mcp_tools():
    """MCP 클라이언트를 위한 도구(Tool) 명세 목록을 반환합니다."""
    return {"tools": get_tools_spec()}


@router.post("/mcp/call", summary="MCP 도구 직접 실행")
async def call_mcp_tool(body: Dict[str, Any], request: Request):
    """MCP 도구를 비동기 커넥션 풀 및 사용자별 쿠키를 통해 안전하게 실행합니다."""
    name = body.get("name")
    arguments = body.get("arguments", {})
    if not name:
        raise HTTPException(status_code=400, detail="'name' 필드는 필수입니다.")
    cookie_override = extract_cookie_override(request)
    set_current_user_cookie(cookie_override, source="http_request")
    result = await async_execute_tool(name, arguments, cookie_override=cookie_override)
    return result


@router.post("/mcp/rpc", summary="MCP JSON-RPC 2.0 엔드포인트")
async def mcp_json_rpc(req: MCPJsonRpcRequest, request: Request):
    """표준 MCP JSON-RPC 2.0 요청(initialize, tools/list, tools/call, ping)을 비동기로 처리합니다."""
    req_id = req.id
    method = req.method
    params = req.params or {}
    cookie_override = extract_cookie_override(request)
    set_current_user_cookie(cookie_override, source="json_rpc")

    # 쿠키가 전혀 없으면 401 + WWW-Authenticate → MCP 클라이언트가 OAuth 브라우저 로그인을 시작
    if config.OAUTH_ENABLED and not get_cookie_header():
        return unauthorized_response(request, req_id)

    if method == "initialize":
        client_version = params.get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_version,
                "serverInfo": {
                    "name": "naverworks-custom-fastapi",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {
                        "listChanged": False
                    }
                }
            }
        }
    elif method == "notifications/initialized":
        return Response(status_code=202)
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": get_tools_spec()
            }
        }
    elif method == "tools/call":
        result = await async_execute_tool(
            params.get("name", ""),
            params.get("arguments", {}),
            cookie_override=cookie_override
        )
        # 네이버웍스가 쿠키를 거부(만료)하면 401로 알려 클라이언트가 다시 로그인하도록 유도
        if config.OAUTH_ENABLED and _is_upstream_unauthorized(result):
            return unauthorized_response(request, req_id)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result
        }
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method}"
            }
        }


@router.get("/sse", summary="MCP SSE 스트림 연결")
async def mcp_sse_stream(request: Request):
    """MCP 클라이언트와 Server-Sent Events 연결을 맺고 세션별 사용자 쿠키를 등록합니다."""
    session_id = str(uuid.uuid4())
    cookie_override = extract_cookie_override(request)

    queue = await session_manager.register(session_id, cookie_override=cookie_override)

    endpoint_url = f"/messages?session_id={session_id}&sessionId={session_id}"
    logger.info(f"📡 [MCP SSE] 신규 세션 연결: session_id={session_id}, 사용자별 쿠키 등록 여부={bool(cookie_override)}")

    async def event_generator():
        try:
            # 1. 클라이언트에 POST 엔드포인트 공지
            yield f"event: endpoint\ndata: {endpoint_url}\n\n"
            while True:
                if await request.is_disconnected():
                    logger.info(f"🔌 [MCP SSE] 클라이언트 정상 종료 감지: session_id={session_id}")
                    break
                try:
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"event: message\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # SSE Keep-Alive ping
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            logger.info(f"🔌 [MCP SSE] 스트림 태스크 취소: session_id={session_id}")
        except Exception as e:
            logger.warning(f"⚠️ [MCP SSE] 스트림 예외: {e}")
        finally:
            await session_manager.unregister(session_id)
            logger.info(f"🧹 [MCP SSE] 세션 리소스 정리 완료: session_id={session_id}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/messages", summary="MCP SSE 메시지 전송 엔드포인트")
async def mcp_sse_messages(
    request: Request,
    session_id: Optional[str] = Query(None, description="세션 ID (snake_case)"),
    sessionId: Optional[str] = Query(None, description="세션 ID (camelCase)")
):
    """SSE 클라이언트로부터 JSON-RPC 메시지를 수신하여 비동기 처리 후 SSE 채널 및 HTTP로 안전하게 응답합니다."""
    sid = session_id or sessionId
    sess = await session_manager.get_session(sid) if sid else None
    if not sess:
        raise HTTPException(status_code=404, detail="유효하지 않거나 이미 종료된 SSE 세션입니다.")

    try:
        body_bytes = await request.body()
        req_data = json.loads(body_bytes.decode("utf-8", "replace")) if body_bytes else {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"유효한 JSON 요청이 아닙니다: {e}")

    req_id = req_data.get("id")
    method = req_data.get("method")
    params = req_data.get("params", {})

    # 쿠키 결정 우선순위: 1) 이번 메시지 요청 헤더 ➔ 2) SSE 핸드셰이크 시 등록된 세션 쿠키 ➔ 3) 서버 기본 쿠키
    cookie_override = extract_cookie_override(request) or sess.cookie_override
    set_current_user_cookie(cookie_override, source="mcp_session")

    response_payload = None
    if method == "initialize":
        client_version = params.get("protocolVersion", "2024-11-05")
        response_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_version,
                "serverInfo": {
                    "name": "naverworks-custom-fastapi",
                    "version": "1.0.0"
                },
                "capabilities": {
                    "tools": {
                        "listChanged": False
                    }
                }
            }
        }
    elif method == "notifications/initialized":
        return Response(status_code=202)
    elif method == "tools/list":
        response_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": get_tools_spec()
            }
        }
    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        # 세션 쿠키 동적 갱신 도구 호출 시 현재 활성 세션 상태도 즉시 업데이트
        if tool_name == "set_user_cookie":
            new_c = arguments.get("cookie")
            cp = arguments.get("cookiePath")
            if cp and not new_c:
                new_c = read_user_cookie_path(cp)
            if new_c:
                sess.cookie_override = new_c.strip()
                cookie_override = sess.cookie_override
                set_current_user_cookie(cookie_override, source="tool_set_user_cookie", cookie_path=cp)

        result = await async_execute_tool(
            tool_name,
            arguments,
            cookie_override=cookie_override
        )
        response_payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result
        }
    elif method == "ping":
        response_payload = {"jsonrpc": "2.0", "id": req_id, "result": {}}
    else:
        if req_id is not None:
            response_payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }

    # MCP SSE 전송 규격(2024-11-05): POST /messages는 202 Accepted만 반환하고,
    # JSON-RPC 응답은 오직 SSE 스트림(event: message)으로만 전달합니다.
    # (HTTP 본문과 SSE 양쪽으로 보내면 클라이언트가 같은 응답을 두 번 처리할 수 있음)
    if response_payload is not None:
        payload_str = json.dumps(response_payload, ensure_ascii=False)
        try:
            await asyncio.wait_for(sess.queue.put(payload_str), timeout=SSE_ENQUEUE_TIMEOUT)
        except asyncio.TimeoutError:
            # 클라이언트가 SSE 스트림을 읽지 않아 큐가 가득 참 → 응답을 조용히 버리지 않고 실패를 알림
            logger.warning(f"⚠️ [MCP] 세션 {sid}의 SSE 큐가 가득 차 응답을 전달하지 못했습니다.")
            raise HTTPException(status_code=503, detail="SSE 스트림이 응답을 소비하지 않아 메시지를 전달할 수 없습니다.")

    return Response(status_code=202, content="Accepted")
