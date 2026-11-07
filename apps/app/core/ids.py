"""네이버웍스 조직 식별 값(domainId, rl) 동적 결정

- domainId: 스페이스/프로젝트/태스크 ID 형식이 `s-{domainId}-{uuid}`, `p-{domainId}-{uuid}`, `t-{domainId}-{uuid}`
  이므로 ID에서 바로 추출합니다. (네트워크 호출 없음)
- rl(instanceCode): 스페이스/프로젝트 응답의 `rl` 필드에서 얻습니다. 프로젝트 조회 응답을 볼 때마다
  projectId → rl 을 기억하고, 모르는 프로젝트는 프로젝트 상세 조회(`/rl/{아무 값}/...` 도 조회됨)로 한 번 확인합니다.

우선순위: 호출자가 명시한 값 → ID/응답에서 얻은 값 → 서버 설정 기본값(NAVERWORKS_DOMAIN_ID / NAVERWORKS_INSTANCE_CODE)
"""

import re
from typing import Any, Dict, Optional

from app.config import DEFAULT_DOMAIN_ID, DEFAULT_INSTANCE_CODE
from app.core.client import async_api_request

_ID_RE = re.compile(r"^[a-z]{1,4}-(\d+)-")

# projectId -> rl. rl은 조직 데이터 위치를 나타내는 공개 식별 값이라 사용자 간 공유해도 무방 (쿠키·데이터 아님)
_RL_CACHE_MAX = 10000
_rl_cache: Dict[str, str] = {}


def domain_from_id(entity_id: Any) -> Optional[str]:
    """`s-300098158-…` 형식의 ID에서 domainId를 추출합니다. 형식이 다르면 None."""
    if not isinstance(entity_id, str):
        return None
    m = _ID_RE.match(entity_id.strip())
    return m.group(1) if m else None


def resolve_domain_id(explicit: Optional[str] = None, *entity_ids: Any) -> str:
    """명시 값 → 첫 번째로 파싱되는 ID의 domainId → 서버 기본값"""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    for eid in entity_ids:
        d = domain_from_id(eid)
        if d:
            return d
    return DEFAULT_DOMAIN_ID


def clear_rl_cache() -> None:
    _rl_cache.clear()


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
