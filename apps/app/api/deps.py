from typing import Dict, Any, Optional
from fastapi import HTTPException, Request
from app.core.cookie import decode_access_token, read_user_cookie_path
from app.core.auth_context import set_current_user_cookie


def handle_response(res: Dict[str, Any]):
    """네이버웍스 API 응답 처리 헬퍼"""
    status = res.get("status", 500)
    if status >= 400:
        raise HTTPException(
            status_code=status,
            detail=res.get("error") or "Unknown error occurred from NAVER WORKS API"
        )
    return res.get("data")


def extract_cookie_override(request: Request) -> Optional[str]:
    """요청 헤더(X-Naverworks-Cookie, X-Naverworks-Cookie-Path), Authorization, 또는 URL Query에서 해당 사용자의 쿠키를 추출합니다."""
    # 1~2. 파일 경로 입력은 서버 호스트의 파일을 가리키므로 local 모드에서만 허용 (read_user_cookie_path)
    # 1. 파일 경로 헤더 (X-Naverworks-Cookie-Path, X-Cookie-Path)
    header_path = request.headers.get("x-naverworks-cookie-path") or request.headers.get("x-cookie-path")
    if header_path and header_path.strip():
        file_cookie = read_user_cookie_path(header_path.strip())
        if file_cookie:
            return file_cookie

    # 2. 파일 경로 쿼리 파라미터 (?cookie_path=..., ?cookie_file=...)
    query_path = request.query_params.get("cookie_path") or request.query_params.get("cookie_file")
    if query_path and query_path.strip():
        file_cookie = read_user_cookie_path(query_path.strip())
        if file_cookie:
            return file_cookie

    # 3. 직접 쿠키 값 헤더 (X-Naverworks-Cookie)
    header_cookie = request.headers.get("x-naverworks-cookie")
    if header_cookie and header_cookie.strip():
        return header_cookie.strip()

    # 4. 직접 쿠키 값 쿼리 파라미터 (?cookie=...)
    query_cookie = request.query_params.get("cookie")
    if query_cookie and query_cookie.strip():
        return query_cookie.strip()

    # 5. Authorization Bearer 헤더 (토큰에 쿠키 문자열이 포함된 경우)
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.strip():
        auth_val = auth_header.strip()
        if auth_val.lower().startswith("bearer "):
            token = auth_val[7:].strip()
            # OAuth로 발급한 토큰(nwc_ + base64url 쿠키)
            decoded = decode_access_token(token)
            if decoded:
                return decoded
            # 쿠키 원문을 그대로 Bearer로 보낸 경우 (이전 방식 호환)
            if "WORKS" in token or "NEO" in token or "=" in token:
                return token

    # 6. 표준 Cookie 헤더 (naverworks 관련 쿠키가 포함된 경우)
    raw_cookie = request.headers.get("cookie")
    if raw_cookie and ("works" in raw_cookie or "NEO" in raw_cookie or "NHN" in raw_cookie):
        return raw_cookie.strip()

    return None


async def bind_request_cookie(request: Request) -> None:
    """REST 요청에 포함된 사용자 쿠키를 현재 요청 컨텍스트(ContextVar)에 바인딩합니다.
    쿠키가 없으면 get_cookie_header()의 기본 우선순위(환경 변수 → 로컬 쿠키 파일)를 따릅니다.
    (async 의존성이어야 엔드포인트와 같은 컨텍스트에서 실행되어 ContextVar가 유지됩니다.)"""
    cookie = extract_cookie_override(request)
    if cookie:
        set_current_user_cookie(cookie, source="http_request")
