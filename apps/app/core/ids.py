"""네이버웍스 조직 식별 값(domainId, rl) 동적 결정

- domainId: 스페이스/프로젝트/태스크 ID 형식이 `s-{domainId}-{uuid}`, `p-{domainId}-{uuid}`, `t-{domainId}-{uuid}`
  이므로 ID에서 바로 추출합니다. (네트워크 호출 없음)
- rl(instanceCode): 스페이스/프로젝트 응답의 `rl` 필드에서 얻습니다. 프로젝트 조회 응답을 볼 때마다
  projectId → rl 을 기억하고, 모르는 프로젝트는 프로젝트 상세 조회(`/rl/{아무 값}/...` 도 조회됨)로 한 번 확인합니다.

- ID가 없는 진입점(list_spaces, create_space, 로그인 검증)의 domainId:
  사용자별로 이전 호출의 ID에서 기억한 값 → 로그인한 네이버웍스 웹 페이지(/space)에서 추출 → NAVERWORKS_DOMAIN_ID(설정한 경우만).
  코드에 박힌 조직 기본값은 없습니다. 끝내 알 수 없으면 DomainIdUnknown 을 던져 호출자에게 domainId/spaceId 를 요청합니다.

우선순위: 호출자가 명시한 값 → ID/응답에서 얻은 값 → 사용자별 기억 값 → 웹 페이지 탐색 → 환경 변수
"""

import hashlib
import re
from collections import Counter
from typing import Any, Dict, Optional, Tuple

from app import config
from app.config import DEFAULT_INSTANCE_CODE
from app.core import client as nw_client
from app.core.client import async_api_request
from app.core.cookie import get_cookie_header

_ID_RE = re.compile(r"^[a-z]{1,4}-(\d+)-")

# projectId -> rl. rl은 조직 데이터 위치를 나타내는 공개 식별 값이라 사용자 간 공유해도 무방 (쿠키·데이터 아님)
_RL_CACHE_MAX = 10000
_rl_cache: Dict[str, str] = {}
# taskId -> rl (태스크 응답의 rl, 또는 태스크가 속한 프로젝트의 rl)
_task_rl_cache: Dict[str, str] = {}


def domain_from_id(entity_id: Any) -> Optional[str]:
    """`s-123456789-…` 형식의 ID에서 domainId를 추출합니다. 형식이 다르면 None."""
    if not isinstance(entity_id, str):
        return None
    m = _ID_RE.match(entity_id.strip())
    return m.group(1) if m else None


class DomainIdUnknown(Exception):
    """조직 ID(domainId)를 결정할 수 없음"""

    message = (
        "네이버웍스 조직 ID(domainId)를 알 수 없습니다. spaceId·projectId·taskId 중 하나를 알려 주거나 "
        "domainId를 직접 지정해 주세요. (서버 운영자는 NAVERWORKS_DOMAIN_ID 환경 변수로 기본값을 줄 수 있습니다.)"
    )

    def __str__(self) -> str:
        return self.message


# 사용자(쿠키 해시) -> domainId. 같은 사용자의 다음 진입점 호출에서 재사용
_USER_DOMAIN_MAX = 10000
_user_domains: Dict[str, str] = {}


def _cookie_key(cookie: Optional[str]) -> Optional[str]:
    return hashlib.sha256(cookie.encode("utf-8")).hexdigest() if cookie else None


def clear_user_domains() -> None:
    _user_domains.clear()


def remember_user_domain(cookie: Optional[str], domain_id: Optional[str]) -> None:
    key = _cookie_key(cookie)
    if key and domain_id and str(domain_id).isdigit():
        if len(_user_domains) >= _USER_DOMAIN_MAX:
            _user_domains.clear()
        _user_domains[key] = str(domain_id)


def learned_domain(cookie: Optional[str]) -> Optional[str]:
    key = _cookie_key(cookie)
    return _user_domains.get(key) if key else None


def resolve_domain_id(explicit: Optional[str] = None, *entity_ids: Any, cookie: Optional[str] = None) -> str:
    """네트워크 호출 없이 결정: 명시 값 → ID에서 추출 → 사용자별 기억 값 → 환경 변수. 모르면 빈 문자열."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    cookie = cookie or get_cookie_header()
    for eid in entity_ids:
        d = domain_from_id(eid)
        if d:
            remember_user_domain(cookie, d)
            return d
    return learned_domain(cookie) or (config.DEFAULT_DOMAIN_ID or "").strip()


# 로그인한 웹 페이지(HTML·서버 렌더링 데이터)에서 domainId 후보를 찾는 패턴
_PAGE_DOMAIN_PATTERNS = (
    re.compile(r"/rd/(\d{3,})/"),
    re.compile(r'"domainId"\s*:\s*"?(\d{3,})'),
)


def _domain_from_page(text: str) -> Optional[str]:
    text = text.replace('\\"', '"')  # Next.js 서버 렌더링 데이터의 이스케이프된 따옴표
    found = Counter(m for pat in _PAGE_DOMAIN_PATTERNS for m in pat.findall(text))
    return found.most_common(1)[0][0] if found else None


async def discover_domain_id(cookie: Optional[str]) -> Tuple[Optional[bool], Optional[str]]:
    """사용자 쿠키로 네이버웍스 웹 페이지(/space)를 열어 (쿠키 유효 여부, domainId)를 알아냅니다.
    로그인 페이지로 돌려보내면 (False, None), 페이지가 열리면 (True, 찾은 domainId 또는 None), 판단 불가면 (None, None)."""
    if not cookie:
        return False, None
    try:
        client = await nw_client.get_async_client()
        resp = await client.get(
            f"{config.BASE_URL}/space",
            headers={"Cookie": cookie, "Accept": "text/html", "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"},
            follow_redirects=False,
        )
    except Exception:
        return None, None
    if 300 <= resp.status_code < 400:
        return ("login" not in resp.headers.get("location", "").lower()) or False, None
    if resp.status_code in (401, 403):
        return False, None
    if resp.status_code != 200:
        return None, None
    return True, _domain_from_page(resp.text)


async def ensure_domain_id(explicit: Optional[str] = None, *entity_ids: Any, cookie: Optional[str] = None) -> str:
    """resolve_domain_id 로 못 정하면 웹 페이지에서 찾고 기억합니다. 끝내 모르면 DomainIdUnknown."""
    cookie = cookie or get_cookie_header()
    domain_id = resolve_domain_id(explicit, *entity_ids, cookie=cookie)
    if domain_id:
        return domain_id
    _, found = await discover_domain_id(cookie)
    if found:
        remember_user_domain(cookie, found)
        return found
    raise DomainIdUnknown()


def clear_rl_cache() -> None:
    _rl_cache.clear()
    _task_rl_cache.clear()


def remember_rl(data: Any) -> None:
    """응답 데이터(프로젝트 객체/목록, `{"project": {...}}` 래핑 포함)에서 projectId → rl 을 기억합니다."""
    stack = [data]
    seen = 0
    while stack and seen < 5000:
        seen += 1
        node = stack.pop()
        if isinstance(node, list):
            stack.extend(node)
        elif isinstance(node, dict):
            pid, rl = node.get("projectId"), node.get("rl")
            if isinstance(pid, str) and pid and rl not in (None, ""):
                if len(_rl_cache) >= _RL_CACHE_MAX:
                    _rl_cache.clear()
                _rl_cache[pid] = str(rl)
            tid = node.get("taskId")
            if isinstance(tid, str) and tid and rl not in (None, ""):
                if len(_task_rl_cache) >= _RL_CACHE_MAX:
                    _task_rl_cache.clear()
                _task_rl_cache[tid] = str(rl)
            stack.extend(v for v in node.values() if isinstance(v, (dict, list)))


def cached_rl(project_id: str) -> Optional[str]:
    return _rl_cache.get(project_id)


async def resolve_project_rl(project_id: str, explicit: Optional[str] = None,
                             cookie_override: Optional[str] = None) -> str:
    """프로젝트의 rl: 명시 값 → 캐시 → 프로젝트 상세 조회 응답 → 서버 기본값"""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    hit = _rl_cache.get(project_id)
    if hit:
        return hit
    res = await async_api_request("GET", f"/rl/{DEFAULT_INSTANCE_CODE}/api/v1/projects/{project_id}",
                                  cookie_override=cookie_override)
    if res.get("status") == 200:
        remember_rl(res.get("data"))
        hit = _rl_cache.get(project_id)
        if hit:
            return hit
    return DEFAULT_INSTANCE_CODE


async def resolve_task_rl(task_id: str, explicit: Optional[str] = None, domain_id: Optional[str] = None,
                          cookie_override: Optional[str] = None) -> str:
    """태스크의 rl: 명시 값 → 태스크 캐시 → 태스크 상세 조회(응답의 rl, 또는 소속 프로젝트의 rl) → 서버 기본값"""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    hit = _task_rl_cache.get(task_id)
    if hit:
        return hit
    if domain_id:
        res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/tasks/{task_id}", cookie_override=cookie_override)
        if res.get("status") == 200:
            data = res.get("data")
            remember_rl(data)
            hit = _task_rl_cache.get(task_id)
            if hit:
                return hit
            task = data.get("task") if isinstance(data, dict) and isinstance(data.get("task"), dict) else data
            project_id = task.get("mainProjectId") or task.get("projectId") if isinstance(task, dict) else None
            if isinstance(project_id, str) and project_id:
                rl = await resolve_project_rl(project_id, None, cookie_override)
                _task_rl_cache[task_id] = rl
                return rl
    return DEFAULT_INSTANCE_CODE


# 사용자(쿠키 해시) -> 메일 사용자 식별자(u)
_user_mail_u: Dict[str, str] = {}


def clear_mail_u_cache() -> None:
    _user_mail_u.clear()


def remember_user_mail_u(cookie: Optional[str], u: Optional[str]) -> None:
    key = _cookie_key(cookie)
    if key and u and str(u).strip():
        if len(_user_mail_u) >= _USER_DOMAIN_MAX:
            _user_mail_u.clear()
        _user_mail_u[key] = str(u).strip()


def learned_mail_u(cookie: Optional[str]) -> Optional[str]:
    key = _cookie_key(cookie)
    return _user_mail_u.get(key) if key else None


def extract_mail_u_from_cookie(cookie: Optional[str]) -> Optional[str]:
    """쿠키 문자열에서 네이버웍스 메일 사용자 식별자(u)로 유력한 값 추출"""
    if not cookie:
        return None
    for part in cookie.split(";"):
        if "=" in part:
            k, v = part.strip().split("=", 1)
            key_clean = k.strip().lower()
            if key_clean in ("works_user_no", "userno", "u", "user_no"):
                val = v.strip()
                if val:
                    return val
            # WORKS_USER_ID가 순수 숫자인 경우 u 후보로 고려
            if key_clean == "works_user_id":
                val = v.strip()
                if val.isdigit() and len(val) >= 10:
                    return val
    return None


def resolve_mail_u(explicit: Optional[str] = None, cookie: Optional[str] = None) -> Optional[str]:
    """메일 사용자 식별자(u): 명시 값 → 이전에 기억한 값 → 쿠키 추출"""
    if explicit and str(explicit).strip():
        val = str(explicit).strip()
        remember_user_mail_u(cookie, val)
        return val
    cookie = cookie or get_cookie_header()
    hit = learned_mail_u(cookie)
    if hit:
        return hit
    from_cookie = extract_mail_u_from_cookie(cookie)
    if from_cookie:
        remember_user_mail_u(cookie, from_cookie)
        return from_cookie
    return None

