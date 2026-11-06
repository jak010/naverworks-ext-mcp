from pathlib import Path
from fastapi import APIRouter, HTTPException
from app.config import is_local_mode
from fastapi.responses import HTMLResponse
from app.core.cookie import refresh_cookie_jar, login_via_browser

router = APIRouter(tags=["System"])

DASHBOARD_HTML_PATH = Path(__file__).resolve().parent.parent / "static" / "dashboard.html"


@router.get("/")
def root():
    return {
        "service": "NAVER WORKS Custom API & MCP Server",
        "status": "online",
        "dashboard_url": "/dashboard",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json"
    }


@router.get("/health")
def health():
    return {"status": "ok"}


def _require_local_mode() -> None:
    """서버 호스트의 키체인/브라우저를 사용하는 엔드포인트는 익명 사용자에게 열지 않습니다."""
    if not is_local_mode():
        raise HTTPException(
            status_code=403,
            detail="다중 사용자 모드에서는 서버 호스트의 쿠키를 갱신할 수 없습니다. 요청 헤더(X-Naverworks-Cookie)로 본인의 쿠키를 전달해 주세요.",
        )


@router.post("/auth/refresh-cookie", tags=["Authentication"])
def refresh_cookie():
    """Chrome KeyChain에서 네이버웍스 최신 쿠키를 추출하여 로컬 쿠키 저장소를 갱신합니다. (local 모드 전용)"""
    _require_local_mode()
    success = refresh_cookie_jar()
    if not success:
        raise HTTPException(status_code=500, detail="쿠키 갱신에 실패했습니다. Chrome 로그인 상태를 확인해주세요.")
    return {"status": "success", "message": "쿠키가 성공적으로 갱신되었습니다."}


@router.post("/auth/browser-login", tags=["Authentication"])
def browser_login(timeout: int = 90, force: bool = False):
    """브라우저를 열어 네이버웍스 로그인을 유도하고 완료 시 쿠키를 자동 감지/저장합니다. (local 모드 전용)"""
    _require_local_mode()
    res = login_via_browser(timeout_seconds=timeout, force=force)
    if not res.get("success"):
        raise HTTPException(status_code=408, detail=res.get("message"))
    return res


@router.get("/dashboard", response_class=HTMLResponse, summary="웹 대시보드 뷰어")
def dashboard():
    """스페이스, 프로젝트, 태스크를 한눈에 볼 수 있는 경량 반응형 웹 대시보드"""
    return DASHBOARD_HTML_PATH.read_text(encoding="utf-8")


