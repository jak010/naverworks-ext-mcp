import time
import json
import hashlib
import asyncio
from typing import Dict, Any, List, Optional
from app.config import (
    is_local_mode,
    BASE_URL,
    DEFAULT_INSTANCE_CODE,
)
from app.core.client import async_api_request
from app.core.payloads import build_task_create_payload
from app.core.cookie import (
    login_via_browser,
    read_user_cookie_path,
    get_cookie_header,
    describe_cookie_source,
)
from app.core.auth_context import set_current_user_cookie
from app.core.ids import resolve_domain_id, resolve_project_rl, remember_rl, cached_rl

# 단기 인메모리 캐시 (LLM의 다중 연속 도구 호출 시 네트워크 지연 0초 실현)
_query_cache: Dict[str, tuple[float, Any]] = {}
CACHE_TTL = 15.0  # 15초 TTL


def get_cached_result(key: str) -> Optional[Any]:
    if key in _query_cache:
        cached_time, val = _query_cache[key]
        if time.time() - cached_time < CACHE_TTL:
            return val
    return None


def set_cached_result(key: str, val: Any) -> None:
    _query_cache[key] = (time.time(), val)


def invalidate_mcp_cache() -> None:
    _query_cache.clear()


LOCAL_LOGIN_DESCRIPTION = (
    "Trigger browser login for NAVER WORKS and automatically capture/decrypt session cookies into local storage. "
    "Use when cookies are missing or expired (401)."
)
REMOTE_LOGIN_DESCRIPTION = (
    "Guide the user through NAVER WORKS login when cookies are missing or expired (401 / UNAUTHORIZED). "
    "Returns a login URL and step-by-step instructions for copying the session cookie. "
    "Show the steps to the user, then call 'set_user_cookie' with the cookie string they paste."
)


MCP_TOOLS_SPEC: List[Dict[str, Any]] = [
    {
        "name": "set_user_cookie",
        "description": "Set or update the active NAVER WORKS cookie for the current MCP session. Allows any user to authenticate with their own cookie string or local cookie file path.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "cookie": {
                    "type": "string",
                    "description": "Raw NAVER WORKS cookie string (e.g. 'WORKS_SES=...; WORKS_USER_ID=...')"
                },
                "cookiePath": {
                    "type": "string",
                    "description": "Absolute or relative path to a local cookie file (Netscape or key=value format)"
                }
            }
        }
    },
    {
        "name": "get_auth_status",
        "description": "Check current authentication status, active cookie source, and user session info for this MCP client.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "login_naverworks",
        "description": LOCAL_LOGIN_DESCRIPTION,
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeoutSeconds": {
                    "type": "integer",
                    "default": 90,
                    "description": "Maximum seconds to wait for user to complete login in browser (default: 90)"
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force open browser login page even if local cookies exist"
                }
            }
        }
    },
    {
        "name": "list_spaces",
        "description": "List all spaces in NAVER WORKS Project (compact summary).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domainId": {"type": "string", "description": "Optional. Defaults to the server setting (NAVERWORKS_DOMAIN_ID)."}
            }
        }
    },
    {
        "name": "get_space",
        "description": "Get detailed information of a specific space.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spaceId": {"type": "string"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["spaceId"]
        }
    },
    {
        "name": "create_space",
        "description": "Create a new space in NAVER WORKS Project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spaceName": {"type": "string"},
                "spaceColor": {"type": "string", "default": "#4694e5"},
                "domainId": {"type": "string", "description": "Optional. Defaults to the server setting (NAVERWORKS_DOMAIN_ID)."}
            },
            "required": ["spaceName"]
        }
    },
    {
        "name": "delete_space",
        "description": "Delete a space permanently.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spaceId": {"type": "string"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["spaceId"]
        }
    },
    {
        "name": "list_projects",
        "description": "List all active projects inside a specific space with their names and IDs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spaceId": {"type": "string", "description": "Space ID to list projects for"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["spaceId"]
        }
    },
    {
        "name": "get_project",
        "description": "Get detailed metadata, views, and custom fields of a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "instanceCode": {"type": "string", "description": "Optional. Resolved automatically from the project (rl); override only if needed."}
            },
            "required": ["projectId"]
        }
    },
    {
        "name": "create_project",
        "description": "Create a new project under a specific space.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "spaceId": {"type": "string"},
                "projectName": {"type": "string"},
                "projectColor": {"type": "string", "default": "#ed7200"},
                "projectType": {"type": "string", "default": "OPEN"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["spaceId", "projectName"]
        }
    },
    {
        "name": "delete_project",
        "description": "Delete a project permanently.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "instanceCode": {"type": "string", "description": "Optional. Resolved automatically from the project (rl); override only if needed."}
            },
            "required": ["projectId"]
        }
    },
    {
        "name": "list_tasks",
        "description": "List all tasks belonging to a specific project (compact summary).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["projectId"]
        }
    },
    {
        "name": "get_task",
        "description": "Get full details and content of a specific task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {"type": "string"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["taskId"]
        }
    },
    {
        "name": "create_task",
        "description": "Create a new task in a project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "projectId": {"type": "string"},
                "title": {"type": "string"},
                "htmlText": {"type": "string", "default": ""},
                "parentTaskId": {"type": "string"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."},
                "rl": {"type": "string", "description": "Optional. Resolved automatically from the project (rl); override only if needed."}
            },
            "required": ["projectId", "title"]
        }
    },
    {
        "name": "update_task_content",
        "description": "Update the content/body of an existing task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {"type": "string"},
                "htmlText": {"type": "string"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["taskId", "htmlText"]
        }
    },
    {
        "name": "delete_task",
        "description": "Delete a task permanently.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "taskId": {"type": "string"},
                "domainId": {"type": "string", "description": "Optional. Derived from the ID automatically; override only if needed."}
            },
            "required": ["taskId"]
        }
    }
]


# ==============================================================================
# LLM 토큰 절감 및 응답 속도 최적화를 위한 데이터 경량화(Slimming) 함수들
# ==============================================================================

def _slim_spaces(data: Any) -> Any:
    """스페이스 목록에서 LLM에게 불필요한 메타데이터를 제거하고 핵심 정보만 추출 (토큰 80%+ 절감)"""
    if not isinstance(data, list):
        return data
    slimmed = []
    for s in data:
        if not isinstance(s, dict):
            continue
        desc = s.get("spaceDescription") or {}
        plain_desc = desc.get("plainText") or desc.get("htmlText") or ""
        rf = s.get("rootFolder") or {}
        children = rf.get("children") or []
        project_ids = [c.get("projectId") for c in children if isinstance(c, dict) and c.get("projectId")]

        slimmed.append({
            "spaceId": s.get("spaceId"),
            "spaceName": s.get("spaceName"),
            "spaceColor": s.get("spaceColor"),
            "description": plain_desc,
            "projectCount": len(project_ids),
            "projectIds": project_ids[:5],
        })
    return slimmed


def _slim_space(data: Any) -> Any:
    """단일 스페이스 상세 정보 경량화"""
    if not isinstance(data, dict):
        return data
    desc = data.get("spaceDescription") or {}
    plain_desc = desc.get("plainText") or desc.get("htmlText") or ""
    rf = data.get("rootFolder") or {}
    children = rf.get("children") or []
    project_ids = [c.get("projectId") for c in children if isinstance(c, dict) and c.get("projectId")]
    return {
        "spaceId": data.get("spaceId"),
        "spaceName": data.get("spaceName"),
        "spaceColor": data.get("spaceColor"),
        "description": plain_desc,
        "projectCount": len(project_ids),
        "projectIds": project_ids,
        "created": data.get("created"),
        "modified": data.get("modified"),
    }


def _slim_projects(data: Any) -> Any:
    """스페이스 하위 프로젝트 목록 경량화 (이름, ID, 색상 등)"""
    if not isinstance(data, list):
        return data
    slimmed = []
    for p in data:
        if not isinstance(p, dict):
            continue
        slimmed.append({
            "projectId": p.get("projectId"),
            "projectName": p.get("projectName"),
            "projectColor": p.get("projectColor"),
            "projectType": p.get("projectType"),
            "status": p.get("status"),
        })
    return slimmed


def _slim_project(data: Any) -> Any:
    """단일 프로젝트 상세 정보 경량화"""
    if not isinstance(data, dict):
        return data
    p = data.get("project", data)
    desc_obj = p.get("description") or {}
    plain_desc = desc_obj.get("plainText") or desc_obj.get("htmlText") or ""
    return {
        "projectId": p.get("projectId"),
        "projectName": p.get("projectName"),
        "projectColor": p.get("projectColor"),
        "projectType": p.get("projectType"),
        "spaceId": p.get("spaceId"),
        "description": plain_desc,
        "created": p.get("created"),
        "modified": p.get("modified"),
    }


def _slim_tasks(data: Any) -> Any:
    """태스크 목록에서 50KB+에 달하는 HTML/유저메타데이터를 제거하고 핵심 정보만 추출 (토큰 70%+ 절감)"""
    if isinstance(data, dict):
        tasks_list = data.get("projectTasks") or data.get("tasks") or []
    elif isinstance(data, list):
        tasks_list = data
    else:
        return data

    slimmed = []
    for t in tasks_list:
        if not isinstance(t, dict):
            continue
        status_val = t.get("taskStatusType") or t.get("status")
        if isinstance(status_val, dict):
            status_val = status_val.get("taskStatusType")

        content_obj = t.get("content") or {}
        preview_text = content_obj.get("plainText") or content_obj.get("htmlText") or ""
        if len(preview_text) > 80:
            preview_text = preview_text[:80] + "..."

        slimmed.append({
            "taskId": t.get("taskId"),
            "title": t.get("title"),
            "status": status_val,
            "due": t.get("due"),
            "parentTaskId": t.get("parentTaskId"),
            "contentPreview": preview_text if preview_text else None,
        })
    return slimmed


def _slim_task(data: Any) -> Any:
    """단일 태스크 상세 정보 경량화
    실제 GET /tasks/{taskId} 응답은 {"task": {...}, "relatedUserIds": [...]} 형태로 감싸져 있습니다."""
    if not isinstance(data, dict):
        return data
    data = data.get("task") if isinstance(data.get("task"), dict) else data
    status_val = data.get("taskStatusType") or data.get("status")
    if isinstance(status_val, dict):
        status_val = status_val.get("taskStatusType")

    content_obj = data.get("content") or {}
    return {
        "taskId": data.get("taskId"),
        "title": data.get("title"),
        "status": status_val,
        "due": data.get("due"),
        "parentTaskId": data.get("parentTaskId"),
        "subTaskIds": data.get("subTaskIds") or [],
        "content": content_obj.get("plainText") or content_obj.get("htmlText") or "",
        "created": data.get("created"),
        "modified": data.get("modified"),
    }


def get_tools_spec() -> List[Dict[str, Any]]:
    """현재 인증 모드에서 사용할 수 있는 도구 명세 목록 (tools/list 응답용)

    login_naverworks는 두 모드 모두 노출하되, multi_user 모드에서는 서버 호스트 브라우저를
    열지 않고 수동 로그인 안내를 반환하므로 설명과 입력 스키마를 그에 맞게 바꿉니다.
    """
    if is_local_mode():
        return MCP_TOOLS_SPEC
    return [
        {**t, "description": REMOTE_LOGIN_DESCRIPTION, "inputSchema": {"type": "object", "properties": {}}}
        if t["name"] == "login_naverworks" else t
        for t in MCP_TOOLS_SPEC
    ]


def _remote_login_guide() -> Dict[str, Any]:
    """multi_user(원격) 모드용 로그인 안내. 서버 호스트의 브라우저·키체인에는 접근하지 않습니다."""
    return {
        "success": False,
        "action": "MANUAL_LOGIN_REQUIRED",
        "loginUrl": BASE_URL,
        "message": (
            "원격 서버는 사용자 PC의 브라우저를 열 수 없습니다. 아래 순서대로 네이버웍스에 로그인한 뒤 "
            "쿠키 문자열을 복사해 대화창에 붙여넣어 주세요."
        ),
        "steps": [
            f"1. 브라우저에서 {BASE_URL} 에 접속해 로그인합니다.",
            "2. 개발자 도구를 엽니다. (Windows/Linux: F12, macOS: Option+Command+I)",
            "3. Network(네트워크) 탭을 열고 페이지를 새로고침합니다.",
            "4. 필터에 'api/v1'을 입력하고 아무 요청이나 클릭합니다.",
            "5. Request Headers의 'cookie:' 값 전체를 복사합니다. ('cookie:' 글자와 따옴표는 제외, WORKS_SES= 포함 확인)",
            "6. 복사한 값을 대화창에 붙여넣으면 'set_user_cookie' 도구로 이 세션에 등록합니다.",
        ],
        "nextTool": "set_user_cookie",
        "persistentSetup": (
            "매번 붙여넣지 않으려면 MCP 클라이언트 설정의 헤더(X-Naverworks-Cookie)에 쿠키를 등록하세요. "
            "Opencode는 쿠키를 파일로 저장하고 {file:~/.config/naverworks/cookie.txt} 로 읽을 수 있습니다."
        ),
    }


def _cookie_fingerprint(cookie: str) -> str:
    return hashlib.sha256(cookie.encode("utf-8")).hexdigest()


def _format_result(data: Any, is_error: bool = False) -> Dict[str, Any]:
    text = json.dumps(data, ensure_ascii=False, indent=2) if isinstance(data, (dict, list)) else str(data)
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


# ==============================================================================
# MCP 도구 실행 핸들러 (비동기)
# ==============================================================================

async def async_execute_tool(
    tool_name: str,
    args: Dict[str, Any],
    cookie_override: Optional[str] = None
) -> Dict[str, Any]:
    """비동기 MCP Tool 호출 핸들러 (커넥션 풀 + 단기 캐시 + 데이터 경량화 + 사용자별 쿠키 오버라이드 지원)"""
    # 0. 인증 및 세션 관리 도구
    if tool_name == "set_user_cookie":
        new_c = args.get("cookie")
        cp = args.get("cookiePath")
        if cp and not new_c:
            new_c = read_user_cookie_path(cp)
        if new_c:
            set_current_user_cookie(new_c.strip(), source="user_tool_update", cookie_path=cp)
            return _format_result({
                "success": True,
                "message": "현재 MCP 세션에 사용자 전용 네이버웍스 쿠키가 등록되었습니다. 이후 모든 도구 호출에 이 쿠키가 사용됩니다.",
                "cookieSource": "user_tool_update",
                "cookieLength": len(new_c.strip())
            })
        return _format_result({
            "success": False,
            "message": "유효한 'cookie' 값 또는 읽을 수 있는 'cookiePath'를 입력해 주세요."
            if is_local_mode() else
            "유효한 'cookie' 값을 입력해 주세요. (다중 사용자 모드에서는 서버 파일 경로 'cookiePath'를 사용할 수 없습니다)"
        }, is_error=True)

    elif tool_name == "get_auth_status":
        active_cookie = cookie_override or get_cookie_header()
        src_info = describe_cookie_source()
        has_cookie = bool(active_cookie and len(active_cookie) > 20)
        cookie_keys = [item.split("=")[0].strip() for item in active_cookie.split(";") if "=" in item]
        return _format_result({
            "isAuthenticated": has_cookie,
            "cookieSource": src_info["source"],
            "cookiePath": src_info["path"],
            "cookieLength": len(active_cookie) if active_cookie else 0,
            "includedTokens": [k for k in cookie_keys if "WORKS" in k or "NEO" in k or "SES" in k]
        })

    elif tool_name == "login_naverworks":
        if not is_local_mode():
            # 원격(multi_user) 모드: 서버 호스트 브라우저 대신 사용자에게 수동 로그인 절차를 안내
            return _format_result(_remote_login_guide())
        timeout = args.get("timeoutSeconds", 90)
        force = args.get("force", False)
        res = await asyncio.to_thread(login_via_browser, timeout_seconds=timeout, force=force)
        return _format_result(res, is_error=not res.get("success", False))

    # 사용자 쿠키 바인딩 보장
    if cookie_override:
        set_current_user_cookie(cookie_override, source="tool_arg_override")

    # 쿠키가 전혀 없는 경우 서버 파일 참조 없이 즉시 401 UNAUTHORIZED 반환 (서버 로컬 쿠키 미사용)
    effective_cookie = cookie_override or get_cookie_header()
    if not effective_cookie or len(effective_cookie) < 20:
        return _format_result({
            "error": "UNAUTHORIZED",
            "message": "사용자 네이버웍스 세션 쿠키가 제공되지 않았습니다. MCP 클라이언트 설정(headers: X-Naverworks-Cookie 또는 X-Naverworks-Cookie-Path)을 등록하거나 'set_user_cookie' 도구를 통해 본인의 쿠키를 전달해 주세요.",
            "nextTool": "login_naverworks",
            "hint": "'login_naverworks' 도구를 호출하면 네이버웍스 로그인 절차를 안내합니다."
        }, is_error=True)

    cache_key = f"{tool_name}:{_cookie_fingerprint(effective_cookie)}:{json.dumps(args, sort_keys=True)}"

    # 1. 스페이스 조회
    if tool_name == "list_spaces":
        cached = get_cached_result(cache_key)
        if cached:
            return _format_result(cached)
        domain_id = resolve_domain_id(args.get("domainId"))
        res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/spaces", cookie_override=cookie_override)
        if res.get("status") == 200:
            remember_rl(res.get("data"))
            slimmed = _slim_spaces(res.get("data"))
            set_cached_result(cache_key, slimmed)
            return _format_result(slimmed)
        return _format_result(res, is_error=True)

    elif tool_name == "get_space":
        space_id = args["spaceId"]
        domain_id = resolve_domain_id(args.get("domainId"), space_id)
        res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/spaces/{space_id}", cookie_override=cookie_override)
        if res.get("status") == 200:
            remember_rl(res.get("data"))
            return _format_result(_slim_space(res.get("data")))
        return _format_result(res, is_error=True)

    elif tool_name == "create_space":
        invalidate_mcp_cache()
        domain_id = resolve_domain_id(args.get("domainId"))
        payload = {
            "spaceName": args["spaceName"],
            "spaceColor": args.get("spaceColor", "#4694e5"),
            "spaceDescription": {"htmlText": "", "plainText": "", "mentionedUserIds": [], "inlineImages": [], "editorVersion": None}
        }
        res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/spaces", payload, cookie_override=cookie_override)
        return _format_result(res.get("data") if res.get("status") == 200 else res, is_error=res.get("status") != 200)

    elif tool_name == "delete_space":
        invalidate_mcp_cache()
        space_id = args["spaceId"]
        domain_id = resolve_domain_id(args.get("domainId"), space_id)
        res = await async_api_request("DELETE", f"/rd/{domain_id}/api/v1/spaces/{space_id}", cookie_override=cookie_override)
        msg = "Space deleted successfully" if res.get("status") == 200 else f"Failed to delete space: {res.get('error')}"
        return _format_result(msg, is_error=res.get("status") != 200)

    # 2. 프로젝트 조회 및 관리
    elif tool_name == "list_projects":
        cached = get_cached_result(cache_key)
        if cached:
            return _format_result(cached)
        space_id = args["spaceId"]
        domain_id = resolve_domain_id(args.get("domainId"), space_id)
        res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/projects?spaceId={space_id}", cookie_override=cookie_override)
        if res.get("status") == 200:
            remember_rl(res.get("data"))
            slimmed = _slim_projects(res.get("data"))
            set_cached_result(cache_key, slimmed)
            return _format_result(slimmed)
        return _format_result(res, is_error=True)

    elif tool_name == "get_project":
        cached = get_cached_result(cache_key)
        if cached:
            return _format_result(cached)
        project_id = args["projectId"]
        # 조회는 instanceCode가 달라도 동작하므로 추가 호출 없이 명시 값 → 캐시 → 기본값 사용
        instance_code = args.get("instanceCode") or cached_rl(project_id) or DEFAULT_INSTANCE_CODE
        res = await async_api_request("GET", f"/rl/{instance_code}/api/v1/projects/{project_id}", cookie_override=cookie_override)
        if res.get("status") == 200:
            remember_rl(res.get("data"))
            slimmed = _slim_project(res.get("data"))
            set_cached_result(cache_key, slimmed)
            return _format_result(slimmed)
        return _format_result(res, is_error=True)

    elif tool_name == "create_project":
        invalidate_mcp_cache()
        domain_id = resolve_domain_id(args.get("domainId"), args["spaceId"])
        payload = {
            "spaceId": args["spaceId"],
            "projectName": args["projectName"],
            "projectColor": args.get("projectColor", "#ed7200"),
            "projectType": args.get("projectType", "OPEN"),
            "spaceProjectParameter": None
        }
        res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/projects", payload, cookie_override=cookie_override)
        if res.get("status") == 200:
            remember_rl(res.get("data"))
        return _format_result(res.get("data") if res.get("status") == 200 else res, is_error=res.get("status") != 200)

    elif tool_name == "delete_project":
        invalidate_mcp_cache()
        project_id = args["projectId"]
        # 쓰기 요청은 프로젝트의 실제 rl 사용 (명시 값 → 캐시 → 프로젝트 조회 → 기본값)
        instance_code = await resolve_project_rl(project_id, args.get("instanceCode"), cookie_override)
        res = await async_api_request("DELETE", f"/rl/{instance_code}/api/v1/projects/{project_id}", cookie_override=cookie_override)
        msg = "Project deleted successfully" if res.get("status") == 200 else f"Failed to delete project: {res.get('error')}"
        return _format_result(msg, is_error=res.get("status") != 200)

    # 3. 태스크 조회 및 관리
    elif tool_name == "list_tasks":
        cached = get_cached_result(cache_key)
        if cached:
            return _format_result(cached)
        project_id = args["projectId"]
        domain_id = resolve_domain_id(args.get("domainId"), project_id)
        res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/tasks?projectId={project_id}", cookie_override=cookie_override)
        if res.get("status") == 200:
            slimmed = _slim_tasks(res.get("data"))
            set_cached_result(cache_key, slimmed)
            return _format_result(slimmed)
        return _format_result(res, is_error=True)

    elif tool_name == "get_task":
        task_id = args["taskId"]
        domain_id = resolve_domain_id(args.get("domainId"), task_id)
        res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/tasks/{task_id}", cookie_override=cookie_override)
        if res.get("status") == 200:
            return _format_result(_slim_task(res.get("data")))
        return _format_result(res, is_error=True)

    elif tool_name == "create_task":
        invalidate_mcp_cache()
        project_id = args["projectId"]
        domain_id = resolve_domain_id(args.get("domainId"), project_id, args.get("parentTaskId"))
        rl = await resolve_project_rl(project_id, args.get("rl"), cookie_override)
        payload = build_task_create_payload(
            project_id, args["title"], args.get("htmlText", ""), args.get("parentTaskId"), domain_id, rl
        )
        res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/tasks", payload, cookie_override=cookie_override)
        return _format_result(res.get("data") if res.get("status") == 200 else res, is_error=res.get("status") != 200)

    elif tool_name == "update_task_content":
        invalidate_mcp_cache()
        task_id = args["taskId"]
        domain_id = resolve_domain_id(args.get("domainId"), task_id)
        payload = {
            "content": {
                "htmlText": args["htmlText"],
                "mentionedUserIds": [],
                "inlineImages": []
            }
        }
        res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/tasks/{task_id}/content", payload, cookie_override=cookie_override)
        msg = "Task content updated successfully" if res.get("status") == 200 else f"Failed to update content: {res.get('error')}"
        return _format_result(msg, is_error=res.get("status") != 200)

    elif tool_name == "delete_task":
        invalidate_mcp_cache()
        task_id = args["taskId"]
        domain_id = resolve_domain_id(args.get("domainId"), task_id)
        res = await async_api_request("DELETE", f"/rd/{domain_id}/api/v1/tasks/{task_id}", cookie_override=cookie_override)
        msg = "Task deleted successfully" if res.get("status") == 200 else f"Failed to delete task: {res.get('error')}"
        return _format_result(msg, is_error=res.get("status") != 200)

    return _format_result(f"Unknown tool: {tool_name}", is_error=True)
