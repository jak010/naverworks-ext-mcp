"""
MCP 표준 OAuth 2.1 인가 흐름 (브라우저 로그인 유도)

쿠키 없이 /mcp/rpc 에 접속한 MCP 클라이언트(Opencode, Cursor, Claude Code 등)는 HTTP 401과
WWW-Authenticate 헤더를 받고, 아래 메타데이터를 따라 사용자의 브라우저로 로그인 페이지(/oauth/authorize)를 엽니다.

네이버웍스 세션 쿠키는 worksmobile.com 도메인의 HttpOnly 쿠키라 이 서버가 브라우저에서 직접 읽을 수 없습니다.
그래서 로그인 페이지에서 사용자가 네이버웍스에 로그인한 뒤 복사한 쿠키 문자열을 붙여넣으면,
서버가 네이버웍스 API로 쿠키를 검증하고 그 쿠키를 access token으로 발급합니다.
(이후 클라이언트는 `Authorization: Bearer <쿠키>` 로 요청하며, 기존 Bearer 쿠키 처리 경로를 그대로 탑니다.)

- 서버는 쿠키를 저장하지 않습니다. 인가 코드(최대 5분, 1회용)만 메모리에 잠시 보관합니다.
- PKCE(S256) 필수.
"""

import base64
import json
import hashlib
import html
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import config
from app.config import BASE_URL, DEFAULT_DOMAIN_ID
from app.core.client import async_api_request

router = APIRouter(tags=["OAuth"])

AUTH_CODE_TTL = 300  # 인가 코드 유효 시간(초)
ACCESS_TOKEN_TTL = 7 * 24 * 3600  # 클라이언트에 알려주는 만료 힌트 (실제 만료는 네이버웍스 세션에 따름)

# code -> {cookie, client_id, redirect_uri, code_challenge, expires_at}
_auth_codes: Dict[str, Dict[str, Any]] = {}


def public_base_url(request: Request) -> str:
    """외부에서 접근하는 서버 기준 URL (리버스 프록시 뒤라면 PUBLIC_BASE_URL 환경 변수로 지정)"""
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}"


def www_authenticate_header(request: Request) -> str:
    return f'Bearer resource_metadata="{public_base_url(request)}/.well-known/oauth-protected-resource"'


def unauthorized_response(request: Request, req_id: Any = None) -> JSONResponse:
    """쿠키 없는 MCP 요청에 대한 401 응답 (클라이언트가 OAuth 브라우저 로그인을 시작하도록 유도)"""
    return JSONResponse(
        status_code=401,
        headers={"WWW-Authenticate": www_authenticate_header(request)},
        content={
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32001,
                "message": "네이버웍스 로그인이 필요합니다. MCP 클라이언트에서 인증(예: `opencode mcp auth naverworks`)을 진행하면 브라우저 로그인 페이지가 열립니다.",
            },
        },
    )


# ------------------------------------------------------------------------------
# 메타데이터 (RFC 9728 / RFC 8414)
# ------------------------------------------------------------------------------

@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/{path:path}")
async def protected_resource_metadata(request: Request, path: str = ""):
    base = public_base_url(request)
    return {
        "resource": f"{base}/mcp/rpc",
        "authorization_servers": [base],
        "bearer_methods_supported": ["header"],
        "resource_name": "NAVER WORKS MCP",
    }


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/{path:path}")
@router.get("/.well-known/openid-configuration")
async def authorization_server_metadata(request: Request, path: str = ""):
    base = public_base_url(request)
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": ["naverworks"],
    }


# ------------------------------------------------------------------------------
# 동적 클라이언트 등록 (RFC 7591) — 공개 클라이언트, 상태 저장 없음
# ------------------------------------------------------------------------------

@router.post("/oauth/register")
async def register_client(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    redirect_uris = body.get("redirect_uris") or []
    if not isinstance(redirect_uris, list) or not all(_valid_redirect_uri(u) for u in redirect_uris):
        return JSONResponse(status_code=400, content={"error": "invalid_redirect_uri"})
    return JSONResponse(status_code=201, content={
        "client_id": f"nw-{secrets.token_urlsafe(16)}",
        "client_id_issued_at": int(time.time()),
        "client_name": body.get("client_name", "MCP Client"),
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
    })


# ------------------------------------------------------------------------------
# 인가 (브라우저 로그인 페이지)
# ------------------------------------------------------------------------------

def _valid_redirect_uri(uri: Any) -> bool:
    if not isinstance(uri, str):
        return False
    parts = urlsplit(uri)
    if parts.scheme == "https" and parts.netloc:
        return True
    # 데스크톱 MCP 클라이언트의 로컬 콜백 서버만 http 허용
    return parts.scheme == "http" and parts.hostname in {"localhost", "127.0.0.1", "::1"}


def _normalize_cookie(raw: str) -> str:
    c = (raw or "").strip()
    if c.lower().startswith("cookie:"):
        c = c[7:].strip()
    if len(c) >= 2 and c[0] == c[-1] and c[0] in "\"'":
        c = c[1:-1].strip()
    return " ".join(c.split())  # 여러 줄로 붙여넣은 경우 한 줄로


def _authorize_params(source: Dict[str, Any]) -> Dict[str, str]:
    keys = ["response_type", "client_id", "redirect_uri", "code_challenge", "code_challenge_method", "state", "scope", "resource"]
    return {k: str(source.get(k) or "") for k in keys}


def _validate_authorize(p: Dict[str, str]) -> Optional[str]:
    if p["response_type"] != "code":
        return "response_type은 code여야 합니다."
    if not p["client_id"]:
        return "client_id가 없습니다."
    if not _valid_redirect_uri(p["redirect_uri"]):
        return "허용되지 않는 redirect_uri 입니다."
    if not p["code_challenge"] or p["code_challenge_method"] != "S256":
        return "PKCE(S256) code_challenge가 필요합니다."
    return None


def _render_login_page(p: Dict[str, str], error: Optional[str] = None, status_code: int = 200) -> HTMLResponse:
    hidden = "\n".join(
        f'<input type="hidden" name="{k}" value="{html.escape(v, quote=True)}">' for k, v in p.items()
    )
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    login_url = html.escape(BASE_URL, quote=True)
    page = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>네이버웍스 MCP 로그인</title>
<style>
:root {{ --bg:#f6f7f9; --card:#fff; --fg:#1d1f23; --muted:#5b6270; --accent:#00a86b; --err:#c62828; --border:#dde1e6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15171a; --card:#1e2125; --fg:#e8eaed; --muted:#9aa0a6; --border:#33373d; --err:#ef5350; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; }}
main {{ max-width:640px; margin:40px auto; padding:0 16px; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:24px; }}
h1 {{ font-size:20px; margin:0 0 8px; }}
ol {{ padding-left:20px; color:var(--muted); }}
li {{ margin:4px 0; }}
code {{ font-size:13px; }}
a.btn, button {{ display:inline-block; background:var(--accent); color:#fff; border:0; border-radius:8px; padding:10px 16px; font-size:15px; text-decoration:none; cursor:pointer; }}
textarea {{ width:100%; box-sizing:border-box; min-height:120px; margin:8px 0 12px; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg); color:var(--fg); font:13px ui-monospace,Menlo,monospace; }}
.err {{ color:var(--err); font-weight:600; }}
.muted {{ color:var(--muted); font-size:13px; }}
</style></head>
<body><main><div class="card">
<h1>네이버웍스 MCP 로그인</h1>
<p class="muted">AI 도구가 내 네이버웍스 프로젝트에 접근하려면 로그인 세션 쿠키가 필요합니다.</p>
<p><a class="btn" href="{login_url}" target="_blank" rel="noopener">1. 네이버웍스 열기 / 로그인</a></p>
<ol>
  <li>열린 네이버웍스 탭에서 로그인합니다.</li>
  <li>개발자 도구를 엽니다. (Windows/Linux: <code>F12</code>, macOS: <code>⌥⌘I</code>)</li>
  <li><b>Network</b> 탭 → 페이지 새로고침 → 필터에 <code>api/v1</code> 입력 → 아무 요청이나 클릭</li>
  <li><b>Request Headers</b>의 <code>cookie:</code> 값 전체를 복사합니다. (<code>WORKS_SES=</code>가 포함되어야 합니다)</li>
</ol>
{err}
<form method="post" action="/oauth/authorize">
{hidden}
<label for="cookie"><b>2. 복사한 쿠키 붙여넣기</b></label>
<textarea id="cookie" name="cookie" required placeholder="WORKS_SES=...; WORKS_USER_ID=...; ..."></textarea>
<button type="submit">로그인 완료</button>
</form>
<p class="muted">쿠키는 이 서버에 저장되지 않고, 검증 후 사용 중인 AI 도구에만 전달됩니다.</p>
</div></main></body></html>"""
    return HTMLResponse(page, status_code=status_code, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})


@router.get("/oauth/authorize", response_class=HTMLResponse)
async def authorize_page(request: Request):
    p = _authorize_params(dict(request.query_params))
    problem = _validate_authorize(p)
    if problem:
        return HTMLResponse(f"<p>잘못된 인증 요청: {html.escape(problem)}</p>", status_code=400)
    return _render_login_page(p)


@router.post("/oauth/authorize", response_class=HTMLResponse)
async def authorize_submit(request: Request):
    form = {k: v[0] for k, v in parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True).items()}
    p = _authorize_params(form)
    problem = _validate_authorize(p)
    if problem:
        return HTMLResponse(f"<p>잘못된 인증 요청: {html.escape(problem)}</p>", status_code=400)

    cookie = _normalize_cookie(form.get("cookie", ""))
    if len(cookie) < 20 or "=" not in cookie:
        return _render_login_page(p, "쿠키 문자열이 비어 있거나 형식이 올바르지 않습니다.", status_code=400)

    # 네이버웍스 API로 쿠키 유효성 확인
    res = await async_api_request("GET", f"/rd/{DEFAULT_DOMAIN_ID}/api/v1/spaces", cookie_override=cookie)
    if res.get("status") != 200:
        return _render_login_page(
            p, f"네이버웍스가 이 쿠키를 거부했습니다 (HTTP {res.get('status')}). 다시 로그인한 뒤 새로 복사해 주세요.",
            status_code=400,
        )

    _purge_expired_codes()
    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "cookie": cookie,
        "client_id": p["client_id"],
        "redirect_uri": p["redirect_uri"],
        "code_challenge": p["code_challenge"],
        "expires_at": time.time() + AUTH_CODE_TTL,
    }
    query = {"code": code}
    if p["state"]:
        query["state"] = p["state"]
    sep = "&" if urlsplit(p["redirect_uri"]).query else "?"
    return RedirectResponse(f"{p['redirect_uri']}{sep}{urlencode(query)}", status_code=303)


# ------------------------------------------------------------------------------
# 토큰 발급
# ------------------------------------------------------------------------------

def _purge_expired_codes() -> None:
    now = time.time()
    for k in [k for k, v in _auth_codes.items() if v["expires_at"] < now]:
        _auth_codes.pop(k, None)


def _token_error(error: str, description: str) -> JSONResponse:
    return JSONResponse(status_code=400, content={"error": error, "error_description": description},
                        headers={"Cache-Control": "no-store"})


@router.post("/oauth/token")
async def token(request: Request):
    raw = (await request.body()).decode("utf-8")
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            form = json.loads(raw or "{}")
        except ValueError:
            form = {}
    else:
        form = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    if form.get("grant_type") != "authorization_code":
        return _token_error("unsupported_grant_type", "authorization_code만 지원합니다. 만료 시 다시 로그인해 주세요.")

    _purge_expired_codes()
    entry = _auth_codes.pop(str(form.get("code") or ""), None)  # 1회용
    if not entry:
        return _token_error("invalid_grant", "인가 코드가 없거나 만료되었습니다.")
    if form.get("redirect_uri") and form.get("redirect_uri") != entry["redirect_uri"]:
        return _token_error("invalid_grant", "redirect_uri가 일치하지 않습니다.")
    if form.get("client_id") and form.get("client_id") != entry["client_id"]:
        return _token_error("invalid_grant", "client_id가 일치하지 않습니다.")

    verifier = str(form.get("code_verifier") or "")
    digest = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii", "ignore")).digest()).rstrip(b"=").decode()
    if not verifier or not secrets.compare_digest(digest, entry["code_challenge"]):
        return _token_error("invalid_grant", "PKCE code_verifier 검증에 실패했습니다.")

    return JSONResponse(
        content={"access_token": entry["cookie"], "token_type": "Bearer", "expires_in": ACCESS_TOKEN_TTL, "scope": "naverworks"},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
