"""
MCP 표준 OAuth 2.1 인가 흐름 (브라우저 로그인 유도)

쿠키 없이 /mcp/rpc 에 접속한 MCP 클라이언트(Opencode, Cursor, Claude Code 등)는 HTTP 401과
WWW-Authenticate 헤더를 받고, 아래 메타데이터를 따라 사용자의 브라우저로 로그인 페이지(/oauth/authorize)를 엽니다.

네이버웍스 세션 쿠키는 worksmobile.com 도메인의 HttpOnly 쿠키라 이 서버가 브라우저에서 직접 읽을 수 없습니다.
그래서 로그인 페이지에서 사용자가 네이버웍스에 로그인한 뒤 복사한 쿠키 문자열을 붙여넣으면,
서버가 네이버웍스 API로 쿠키를 검증하고 그 쿠키를 access token으로 발급합니다.
사용자는 네이버웍스 요청을 "Copy as cURL"로 복사해 붙여넣고, 서버는 여기서 쿠키와 조직 ID(요청 URL의 /rd/{domainId}/)를 함께 얻습니다.
access token은 `nwt_` + base64url({"c": 쿠키, "d": 조직 ID}) 형식이라 요청마다 조직 ID가 함께 전달됩니다 (서버 재시작에도 유지).
쿠키 원문의 공백과 ';'이 Bearer 토큰 형식(RFC 6750)에 맞지 않아 base64url로 감쌉니다.

- 서버는 쿠키를 저장하지 않습니다. 인가 코드(최대 5분, 1회용)만 메모리에 잠시 보관합니다.
- PKCE(S256) 필수.
"""

import base64
import json
import hashlib
import html
import re
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import config
from app.config import BASE_URL
from app.core.client import async_api_request
from app.core.cookie import encode_access_token
from app.core.ids import discover_domain_id, remember_user_domain, resolve_domain_id

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

_PRIVATE_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*$")
_BLOCKED_SCHEMES = {"javascript", "data", "file", "vbscript", "about", "blob", "ftp", "ws", "wss"}


def _valid_redirect_uri(uri: Any) -> bool:
    if not isinstance(uri, str):
        return False
    parts = urlsplit(uri)
    scheme = parts.scheme.lower()
    if scheme == "https" and parts.netloc:
        return True
    # 데스크톱 MCP 클라이언트의 로컬 콜백 서버만 http 허용
    if scheme == "http":
        return parts.hostname in {"localhost", "127.0.0.1", "::1"}
    # 네이티브 앱 전용 스킴 (RFC 8252 7.1, 예: cursor://, vscode://). 인가 코드는 PKCE로 보호됨
    return bool(_PRIVATE_SCHEME_RE.match(scheme)) and scheme not in _BLOCKED_SCHEMES


def _normalize_cookie(raw: str) -> str:
    c = (raw or "").strip()
    if c.lower().startswith("cookie:"):
        c = c[7:].strip()
    if len(c) >= 2 and c[0] == c[-1] and c[0] in "\"'":
        c = c[1:-1].strip()
    return " ".join(c.split())  # 여러 줄로 붙여넣은 경우 한 줄로


_RD_DOMAIN_RE = re.compile(r"/rd/(\d{3,})/")
# "Copy as cURL"의 쿠키: bash/zsh (-b '...', -H 'cookie: ...') · Windows cmd (^"...^")
_CURL_COOKIE_RES = (
    re.compile(r"""(?:-H|--header)\s+(['"])cookie:\s*(.*?)\1""", re.I | re.S),
    re.compile(r"""(?:-b|--cookie)\s+(['"])(.*?)\1""", re.S),
)
# "Copy as PowerShell"의 쿠키: $session.Cookies.Add((New-Object System.Net.Cookie("이름", "값", ...)))
_PS_COOKIE_RE = re.compile(r"""System\.Net\.Cookie\(\s*"((?:[^"\\]|\\.)*)"\s*,\s*"((?:[^"\\]|\\.)*)\"""", re.S)


def _looks_like_curl(text: str) -> bool:
    return bool(re.search(r"(^|\s)curl(\.exe)?\s", text.strip() + " ", re.I)) or text.lstrip().lower().startswith("curl")


def _looks_like_powershell(text: str) -> bool:
    return "System.Net.Cookie" in text or "Microsoft.PowerShell" in text


def _cookie_from_powershell(text: str) -> str:
    """PowerShell 복사본의 System.Net.Cookie(...) 호출들을 name=value 로 모읍니다."""
    pairs = []
    for name, value in _PS_COOKIE_RE.findall(text):
        name = name.replace('\\"', '"').replace("`\"", '"').strip()
        value = value.replace('\\"', '"').replace("`\"", '"').strip()
        if name:
            pairs.append(f"{name}={value}")
    return "; ".join(pairs)


def parse_login_input(pasted: str) -> "tuple[str, Optional[str]]":
    """로그인 페이지 입력에서 (쿠키, 조직 ID)를 꺼냅니다.
    - "Copy as cURL" / "Copy as PowerShell" 전체를 붙여넣으면 쿠키를 꺼내고, 주소에 /rd/{조직 ID}/ 가 있으면 조직 ID도 함께 얻습니다.
    - 쿠키 값만 붙여넣어도 됩니다. 이때 조직 ID는 None 이며, 서버가 로그인한 웹 페이지에서 자동으로 찾습니다."""
    text = pasted or ""
    m = _RD_DOMAIN_RE.search(text)
    domain = m.group(1) if m else None

    if _looks_like_curl(text):
        unescaped = text.replace("^\"", "\"").replace("^%", "%").replace("^&", "&").replace("^", "") if '^"' in text else text
        cookie = ""
        for pat in _CURL_COOKIE_RES:
            m = pat.search(unescaped)
            if m:
                cookie = m.group(2)
                break
    elif _looks_like_powershell(text):
        cookie = _cookie_from_powershell(text)
    else:
        cookie = text
    return _normalize_cookie(cookie), domain


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


# 붙여넣는 즉시 세션 쿠키 포함 여부를 알려 주는 클라이언트 검증 (서버 검증을 대체하지 않음, 실패 왕복만 줄임)
_LOGIN_SCRIPT = """<script>
(function () {
  var ta = document.getElementById('cookie');
  var status = document.getElementById('cookie-status');
  if (!ta || !status) return;
  function update() {
    var v = (ta.value || '').trim();
    if (!v) { status.textContent = ''; status.className = 'muted'; return; }
    if (/WORKS_SES=/.test(v)) {
      status.textContent = '\\u2713 네이버웍스 세션을 찾았습니다. [로그인 완료]를 누르세요.';
      status.className = 'ok';
    } else if (/[^=\\s;]+=[^;]+/.test(v)) {
      status.textContent = '세션 쿠키(WORKS_SES)가 보이지 않습니다. 네이버웍스에 로그인된 상태의 요청을 복사했는지 확인하세요. 그대로 제출하면 서버가 다시 확인합니다.';
      status.className = 'warn';
    } else {
      status.textContent = '쿠키를 찾지 못했습니다. 요청을 마우스 오른쪽 클릭 → Copy → Copy as cURL 로 복사해 붙여넣으세요.';
      status.className = 'warn';
    }
  }
  ta.addEventListener('input', update);
  ta.addEventListener('paste', function () { setTimeout(update, 0); });
})();
</script>"""


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
:root {{ --bg:#f6f7f9; --card:#fff; --fg:#1d1f23; --muted:#5b6270; --accent:#00a86b; --err:#c62828; --warn:#b26a00; --border:#dde1e6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#15171a; --card:#1e2125; --fg:#e8eaed; --muted:#9aa0a6; --border:#33373d; --err:#ef5350; --warn:#e0a030; }} }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.6 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif; }}
main {{ max-width:640px; margin:40px auto; padding:0 16px; }}
.card {{ background:var(--card); border:1px solid var(--border); border-radius:12px; padding:24px; }}
h1 {{ font-size:20px; margin:0 0 8px; }}
ol {{ padding-left:20px; color:var(--muted); }}
li {{ margin:4px 0; }}
code {{ font-size:13px; }}
a.btn, button {{ display:inline-block; background:var(--accent); color:#fff; border:0; border-radius:8px; padding:10px 16px; font-size:15px; text-decoration:none; cursor:pointer; }}
input {{ width:100%; box-sizing:border-box; margin:8px 0 12px; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg); color:var(--fg); font:13px ui-monospace,Menlo,monospace; }}
textarea {{ width:100%; box-sizing:border-box; min-height:120px; margin:8px 0 12px; padding:10px; border:1px solid var(--border); border-radius:8px; background:var(--bg); color:var(--fg); font:13px ui-monospace,Menlo,monospace; }}
.err {{ color:var(--err); font-weight:600; }}
.muted {{ color:var(--muted); font-size:13px; }}
#cookie-status {{ min-height:20px; margin:-4px 0 12px; font-size:13px; }}
#cookie-status.ok {{ color:var(--accent); font-weight:600; }}
#cookie-status.warn {{ color:var(--warn); }}
</style></head>
<body><main><div class="card">
<h1>네이버웍스 MCP 로그인</h1>
<p class="muted">AI 도구가 내 네이버웍스 프로젝트에 접근하려면 로그인 세션 쿠키가 필요합니다.</p>
<p><a class="btn" href="{login_url}" target="_blank" rel="noopener">1. 네이버웍스 열기 / 로그인</a></p>
<ol>
  <li>열린 네이버웍스 탭에서 로그인합니다.</li>
  <li>개발자 도구를 엽니다. (Windows/Linux: <code>F12</code>, macOS: <code>⌥⌘I</code>)</li>
  <li><b>Network</b> 탭 → 페이지 새로고침 → 목록에 뜨는 <b>아무 요청이나</b> 마우스 오른쪽 클릭 → <b>Copy → Copy as cURL</b></li>
</ol>
<p class="muted">특정 요청을 고르거나 필터를 걸 필요 없이, 로그인된 상태의 요청이면 됩니다. (Windows는 <i>Copy as cURL (bash)</i>, PowerShell 복사본도 됩니다.)
조직 ID는 서버가 자동으로 찾습니다.</p>
{err}
<form method="post" action="/oauth/authorize">
{hidden}
<label for="cookie"><b>2. 복사한 cURL(또는 쿠키) 붙여넣기</b></label>
<textarea id="cookie" name="cookie" required placeholder="curl 'https://project.worksmobile.com/...' -H '...' -b 'WORKS_SES=...'"></textarea>
<div id="cookie-status" class="muted" aria-live="polite"></div>
<button type="submit">로그인 완료</button>
</form>
<p class="muted">쿠키와 조직 ID는 이 서버에 저장되지 않고, 검증 후 사용 중인 AI 도구에만 전달됩니다.</p>
</div></main>{_LOGIN_SCRIPT}</body></html>"""
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

    cookie, domain_id = parse_login_input(form.get("cookie", ""))
    if len(cookie) < 20 or "=" not in cookie:
        return _render_login_page(
            p, "쿠키를 찾지 못했습니다. 요청을 'Copy as cURL'로 복사했는지, 또는 cookie: 값 전체를 붙여넣었는지 확인해 주세요.",
            status_code=400,
        )

    # 조직 ID: 붙여넣은 cURL의 주소 → (없으면) 로그인한 웹 페이지 → 서버 설정
    if not domain_id:
        valid, found = await discover_domain_id(cookie)
        if valid is False:
            return _render_login_page(p, "네이버웍스가 이 쿠키를 거부했습니다. 다시 로그인한 뒤 새로 복사해 주세요.", status_code=400)
        domain_id = found or resolve_domain_id(None, cookie=cookie)
    if not domain_id:
        return _render_login_page(
            p, "조직 ID를 찾지 못했습니다. Network 탭 필터에 /rd/ 를 입력해 주소에 /rd/숫자/ 가 있는 요청을 고른 뒤, "
               "'Copy as cURL'로 복사해 다시 붙여넣어 주세요.",
            status_code=400,
        )

    # 쿠키 유효성 확인 (해당 조직의 스페이스 목록 조회)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/spaces", cookie_override=cookie)
    if res.get("status") != 200:
        return _render_login_page(
            p, f"네이버웍스가 이 쿠키를 거부했습니다 (HTTP {res.get('status')}). 다시 로그인한 뒤 새로 복사해 주세요.",
            status_code=400,
        )
    remember_user_domain(cookie, domain_id)

    _purge_expired_codes()
    code = secrets.token_urlsafe(32)
    _auth_codes[code] = {
        "cookie": cookie,
        "domain_id": domain_id,
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
        content={"access_token": encode_access_token(entry["cookie"], entry.get("domain_id")), "token_type": "Bearer", "expires_in": ACCESS_TOKEN_TTL, "scope": "naverworks"},
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
