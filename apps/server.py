#!/usr/bin/env python3
"""
NAVER WORKS Spaces & Project MCP Server (Stdio JSON-RPC)
Compliant with Model Context Protocol (MCP) 2024-11-05 specification.
Directly callable by Antigravity IDE, Claude Desktop, Cursor, and any MCP client.
"""

import os
import sys

# 1. 가상환경(.venv) 파이썬 자동 감지 및 re-exec (글로벌 python3로 실행되어도 venv 패키지 자동 활용)
APPS_DIR = os.path.dirname(os.path.abspath(__file__))      # <repo>/apps  (app 패키지 위치)
REPO_ROOT = os.path.dirname(APPS_DIR)                      # <repo>       (.venv 위치)
VENV_PYTHON = os.path.join(REPO_ROOT, ".venv", "bin", "python")
if os.path.exists(VENV_PYTHON) and sys.executable != VENV_PYTHON:
    os.execv(VENV_PYTHON, [VENV_PYTHON] + sys.argv)

if APPS_DIR not in sys.path:
    sys.path.insert(0, APPS_DIR)

# stdio 서버는 MCP 클라이언트가 사용자 본인 PC에서 직접 실행하는 단일 사용자용이므로 로컬 모드가 기본입니다.
# (app 모듈 import 전에 설정해야 반영됨)
os.environ.setdefault("NAVERWORKS_AUTH_MODE", "local")

import json
import asyncio
import logging
from app.core.mcp_spec import get_tools_spec, async_execute_tool
from app.config import is_local_mode

# 모든 로깅은 stderr로 전달 (stdout은 순수 JSON-RPC 통신 전용)
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [naverworks-mcp] %(message)s"
)
logger = logging.getLogger("mcp-stdio")


async def handle_request(req: dict) -> dict | None:
    req_id = req.get("id")
    method = req.get("method")
    params = req.get("params") or {}

    if method == "initialize":
        client_version = params.get("protocolVersion", "2024-11-05")
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_version,
                "serverInfo": {
                    "name": "naverworks-project",
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
        # 알림(Notification)은 응답 불필요
        return None

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": get_tools_spec()
            }
        }

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        result = await async_execute_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result
        }

    elif method == "ping":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {}
        }

    else:
        if req_id is not None:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                }
            }
        return None


async def main_async():
    logger.info("NAVER WORKS MCP Stdio Server 시작됨 (local 모드: 사용자 PC의 쿠키 파일 사용)" if is_local_mode() else "NAVER WORKS MCP Stdio Server 시작됨 (multi_user 모드: 요청별 사용자 쿠키 필수)")

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    while True:
        line_bytes = await reader.readline()
        if not line_bytes:
            logger.info("입력 스트림(EOF) 종료됨")
            break

        line = line_bytes.decode("utf-8", "replace").strip()
        if not line:
            continue

        try:
            req = json.loads(line)
        except Exception as e:
            logger.warning(f"JSON 파싱 오류: {e} (입력: {line[:100]})")
            continue

        try:
            resp = await handle_request(req)
            if resp is not None:
                out = json.dumps(resp, ensure_ascii=False) + "\n"
                sys.stdout.write(out)
                sys.stdout.flush()
        except Exception as e:
            logger.error(f"요청 처리 중 예외 발생: {e}", exc_info=True)
            if req.get("id") is not None:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": req.get("id"),
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {e}"
                    }
                }
                sys.stdout.write(json.dumps(err_resp, ensure_ascii=False) + "\n")
                sys.stdout.flush()


def main():
    try:
        asyncio.run(main_async())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()

