import os
import json
import asyncio
import hashlib
import weakref
import urllib.parse
import urllib.request
import urllib.error
import httpx
from typing import Optional, Any, Dict
from app.config import BASE_URL
from app.core.cookie import get_cookie_header

# 전역 비동기 HTTP 커넥션 풀 및 동시성 제어 세마포어
_async_client: Optional[httpx.AsyncClient] = None
_client_loop: Optional[asyncio.AbstractEventLoop] = None
_client_lock = asyncio.Lock()

# 네이버웍스 업스트림 서버 부하 방지 및 429 Rate Limit 방어용 전역 세마포어 (서버 전체 최대 동시 요청 수)
UPSTREAM_MAX_CONCURRENCY = int(os.getenv("NAVERWORKS_UPSTREAM_CONCURRENCY", 25))
# 사용자(쿠키)별 최대 동시 요청 수: 한 사용자가 전역 슬롯을 독점해 다른 사용자를 지연시키지 못하도록 제한
PER_USER_MAX_CONCURRENCY = int(os.getenv("NAVERWORKS_PER_USER_CONCURRENCY", 4))
# (이벤트 루프, 쿠키 해시) → 세마포어. 사용 중인 요청이 없으면 자동으로 정리됨 (WeakValueDictionary)
_user_semaphores: "weakref.WeakValueDictionary[tuple, asyncio.Semaphore]" = weakref.WeakValueDictionary()
_upstream_semaphore: Optional[asyncio.Semaphore] = None
_semaphore_loop: Optional[asyncio.AbstractEventLoop] = None


def get_upstream_semaphore() -> asyncio.Semaphore:
    global _upstream_semaphore, _semaphore_loop
    current_loop = asyncio.get_running_loop()
    if _upstream_semaphore is None or _semaphore_loop != current_loop:
        _upstream_semaphore = asyncio.Semaphore(UPSTREAM_MAX_CONCURRENCY)
        _semaphore_loop = current_loop
    return _upstream_semaphore


def get_user_semaphore(cookie_header: str) -> asyncio.Semaphore:
    """사용자(쿠키)별 동시성 세마포어를 반환합니다. 호출자가 참조를 유지하는 동안만 살아 있습니다."""
    key = (id(asyncio.get_running_loop()), hashlib.sha256(cookie_header.encode("utf-8")).hexdigest())
    sem = _user_semaphores.get(key)
    if sem is None:
        sem = asyncio.Semaphore(PER_USER_MAX_CONCURRENCY)
        _user_semaphores[key] = sem
    return sem


async def get_async_client() -> httpx.AsyncClient:
    """커넥션 풀이 적용된 재사용 가능한 싱글톤 httpx.AsyncClient를 반환합니다. (이벤트 루프 안전성 보장)"""
    global _async_client, _client_loop
    current_loop = asyncio.get_running_loop()
    if _async_client is None or _async_client.is_closed or _client_loop != current_loop:
        limits = httpx.Limits(
            max_connections=100,
            max_keepalive_connections=25,
            keepalive_expiry=30.0,
        )
        timeout = httpx.Timeout(30.0, connect=10.0)
        _async_client = httpx.AsyncClient(
            limits=limits,
            timeout=timeout,
            http2=False,  # 호환성 최적화
        )
        _client_loop = current_loop
    return _async_client


async def close_async_client() -> None:
    """서버 종료 시 커넥션 풀을 안전하게 닫습니다."""
    global _async_client
    if _async_client is not None and not _async_client.is_closed:
        await _async_client.aclose()
        _async_client = None


def api_request(
    method: str,
    path: str,
    data: Optional[Dict[str, Any]] = None,
    cookie_override: Optional[str] = None,
    base_url: Optional[str] = None,
    form_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute synchronous API request against NAVER WORKS using the active MCP user's cookie."""
    cookie_header = cookie_override if cookie_override else get_cookie_header()
    if not cookie_header:
        return {
            "status": 401,
            "error": "사용자 네이버웍스 쿠키가 설정되지 않았습니다. MCP 클라이언트 설정(headers) 또는 'set_user_cookie' 도구를 사용해 쿠키를 전달해주세요."
        }

    if path.startswith(("http://", "https://")):
        url = path
    elif base_url:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    else:
        url = f"{BASE_URL}{path}"

    headers = {
        "Cookie": cookie_header,
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    }
    if "mail.worksmobile.com" in url:
        headers["Referer"] = "https://mail.worksmobile.com/"
        headers["Origin"] = "https://mail.worksmobile.com"

    body = None
    if form_data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        body = urllib.parse.urlencode(form_data).encode("utf-8")
    elif data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, headers=headers, data=body, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30.0) as resp:
            res = resp.read().decode("utf-8")
            return {
                "status": resp.status,
                "data": json.loads(res) if res else None
            }
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", "replace")
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = err_body
        return {"status": e.code, "error": err_json}
    except Exception as e:
        return {"status": 500, "error": str(e)}


async def async_api_request(
    method: str,
    path: str,
    data: Optional[Dict[str, Any]] = None,
    cookie_override: Optional[str] = None,
    base_url: Optional[str] = None,
    form_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Execute asynchronous API request using shared connection pool with the active MCP user's cookie."""
    cookie_header = cookie_override if cookie_override else get_cookie_header()
    if not cookie_header:
        return {
            "status": 401,
            "error": "사용자 네이버웍스 쿠키가 설정되지 않았습니다. MCP 클라이언트 설정(headers) 또는 'set_user_cookie' 도구를 사용해 쿠키를 전달해주세요."
        }

    if path.startswith(("http://", "https://")):
        url = path
    elif base_url:
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    else:
        url = f"{BASE_URL}{path}"

    client = await get_async_client()
    semaphore = get_upstream_semaphore()
    user_semaphore = get_user_semaphore(cookie_header)

    headers = {
        "Cookie": cookie_header,
        "Accept": "application/json, text/plain, */*",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    }
    if "mail.worksmobile.com" in url:
        headers["Referer"] = "https://mail.worksmobile.com/"
        headers["Origin"] = "https://mail.worksmobile.com"

    req_kwargs: Dict[str, Any] = {
        "method": method,
        "url": url,
        "headers": headers,
    }
    if form_data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded; charset=UTF-8"
        req_kwargs["data"] = form_data
    elif data is not None:
        req_kwargs["json"] = data

    try:
        # 사용자 슬롯을 먼저 확보한 뒤 전역 슬롯을 잡음 → 자기 차례를 기다리는 동안 전역 슬롯을 점유하지 않음
        async with user_semaphore, semaphore:
            resp = await client.request(**req_kwargs)
            if resp.status_code >= 400:
                try:
                    err_json = resp.json()
                except Exception:
                    err_json = resp.text
                return {"status": resp.status_code, "error": err_json}

            if resp.text:
                try:
                    return {"status": resp.status_code, "data": resp.json()}
                except Exception:
                    return {"status": resp.status_code, "data": resp.text}
            return {"status": resp.status_code, "data": None}
    except Exception as e:
        return {"status": 500, "error": str(e)}
