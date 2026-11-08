import os
import re
import time
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from urllib.parse import urlsplit
from app import config
from app.config import is_local_mode
from app.core.client import close_async_client
from app.core.ids import DomainIdUnknown
from app.api.system import router as system_router
from app.api.v1 import v1_router
from app.api.mcp import router as mcp_router
from app.api.oauth import router as oauth_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("app")


class RedactCookieQueryFilter(logging.Filter):
    """접근 로그에서 ?cookie=... 쿼리 값을 가립니다. (사용자 세션 쿠키가 서버 로그에 평문으로 남지 않도록)"""

    _pattern = re.compile(r"([?&]cookie=)[^&\s]*", re.IGNORECASE)

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(
                self._pattern.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args
            )
        elif isinstance(record.msg, str):
            record.msg = self._pattern.sub(r"\1***", record.msg)
        return True


def install_log_redaction() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, RedactCookieQueryFilter) for f in access_logger.filters):
        access_logger.addFilter(RedactCookieQueryFilter())


install_log_redaction()


@asynccontextmanager
async def lifespan(app: FastAPI):
    install_log_redaction()  # uvicorn 로깅 설정 이후에도 필터가 유지되도록 재확인
    # 서버 기동 시 안내 (요청별/세션별 사용자 쿠키 기반 인증 모드)
    mode = "local (단일 사용자: 서버 로컬 쿠키 사용)" if is_local_mode() else "multi_user (익명 다중 사용자: 요청별 사용자 쿠키 필수)"
    logger.info(f"🚀 NAVER WORKS MCP 서버가 시작되었습니다. 인증 모드: {mode}")
    if is_local_mode() and os.getenv("HOST", config.HOST) not in ("127.0.0.1", "localhost", "::1"):
        logger.warning("⚠️ local 모드인데 루프백이 아닌 주소에 바인드되었습니다. 같은 네트워크의 누구나 서버 호스트의 네이버웍스 쿠키로 요청할 수 있습니다.")
    yield
    # 서버 종료 시 비동기 HTTP 커넥션 풀 안전하게 종료
    logger.info("🛑 네이버웍스 비동기 커넥션 풀 정리 중...")
    await close_async_client()
    logger.info("👋 서버 리소스 정리 완료")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """다중 동시 요청 시 요청 추적(Correlation ID) 및 응답 소요 시간 헤더 주입 미들웨어"""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        start_time = time.time()
        response = await call_next(request)
        process_time_ms = (time.time() - start_time) * 1000
        response.headers["X-Request-ID"] = req_id
        response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"
        return response


class LocalOriginGuard:
    """local 모드 전용 보호 (순수 ASGI 미들웨어 — SSE 스트리밍에 영향 없음)

    local 모드에서는 쿠키 없는 요청에 서버 호스트(사용자 본인)의 네이버웍스 쿠키가 사용됩니다.
    따라서 사용자가 방문한 임의의 웹페이지가 브라우저를 통해 localhost 서버를 호출하는 것을 막아야 합니다.
      - Host 헤더가 허용 목록에 없으면 거부  → DNS rebinding 차단
      - Origin 헤더가 있고 허용 목록에 없으면 거부 → 교차 출처 웹페이지의 요청 차단 (CORS preflight 없는 단순 요청 포함)
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and is_local_mode():
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            allowed = config.LOCAL_ALLOWED_HOSTS
            host = urlsplit("//" + headers.get("host", "")).hostname or ""
            origin = headers.get("origin")
            origin_host = urlsplit(origin).hostname if origin and origin != "null" else None
            if host not in allowed or (origin is not None and origin_host not in allowed):
                body = b'{"status":403,"error":"Forbidden","message":"local mode accepts requests from localhost only"}'
                await send({"type": "http.response.start", "status": 403,
                            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)


app = FastAPI(
    title="NAVER WORKS Custom API & MCP Server",
    description="네이버웍스 Project / Spaces / Tasks를 손쉽게 제어할 수 있는 고성능·안전한 FastAPI 기반 REST API & MCP 서버입니다.",
    version="1.0.0",
    lifespan=lifespan,
)

# 1. 다중 요청 추적 미들웨어 등록
app.add_middleware(RequestContextMiddleware)

# 2. CORS 설정: 명시적으로 허용한 Origin만 (기본값: 교차 출처 불허). 인증은 쿠키가 아닌 커스텀 헤더이므로 credentials 불필요.
if config.CORS_ALLOW_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ALLOW_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization", "X-Naverworks-Cookie", "X-Naverworks-Domain-Id", "X-Request-ID"],
    )

# 3. local 모드 Host/Origin 검증 (가장 바깥에서 실행되도록 마지막에 등록)
app.add_middleware(LocalOriginGuard)


# 조직 ID를 알 수 없는 REST 요청 → 400 (domainId 또는 ID를 지정하도록 안내)
@app.exception_handler(DomainIdUnknown)
async def domain_unknown_handler(request: Request, exc: DomainIdUnknown):
    return JSONResponse(status_code=400, content={"status": 400, "error": "DOMAIN_ID_UNKNOWN", "message": str(exc)})


# 4. 전역 예외 처리기 (예상치 못한 에러 시에도 일관된 JSON 에러 응답 및 서버 크래시 방지)
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ [Unhandled Error] {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "status": 500,
            "error": "Internal Server Error",
            "message": str(exc),
        }
    )


# 5. 라우터 등록
app.include_router(system_router)
app.include_router(v1_router)
app.include_router(mcp_router)
app.include_router(oauth_router)
