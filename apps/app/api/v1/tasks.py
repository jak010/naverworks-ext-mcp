from typing import Optional
from fastapi import APIRouter, Query, Path
from app.core.ids import resolve_domain_id, resolve_project_rl
from app.core.payloads import build_task_create_payload
from app.core.client import async_api_request
from app.schemas.task import TaskCreateRequest, TaskContentUpdateRequest
from app.api.deps import handle_response

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", summary="태스크 목록 조회")
async def list_tasks(
    project_id: str = Query(..., description="소속 프로젝트 ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """특정 프로젝트에 속한 전체 태스크 목록을 조회합니다."""
    domain_id = resolve_domain_id(domain_id, project_id)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/tasks?projectId={project_id}")
    return handle_response(res)


@router.get("/{task_id}", summary="태스크 상세 조회")
async def get_task(
    task_id: str = Path(..., description="태스크 ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """특정 태스크의 상세 정보, 본문 및 하위 작업 목록을 조회합니다."""
    domain_id = resolve_domain_id(domain_id, task_id)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/tasks/{task_id}")
    return handle_response(res)


@router.post("", summary="신규 태스크 생성")
async def create_task(payload: TaskCreateRequest):
    """신규 태스크 또는 하위 태스크를 생성합니다."""
    domain_id = resolve_domain_id(payload.domainId, payload.projectId, payload.parentTaskId)
    rl = await resolve_project_rl(payload.projectId, payload.rl)
    body = build_task_create_payload(
        payload.projectId, payload.title, payload.htmlText, payload.parentTaskId, domain_id, rl
    )
    res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/tasks", body)
    return handle_response(res)


@router.put("/{task_id}/content", summary="태스크 본문 수정")
@router.post("/{task_id}/content", summary="태스크 본문 수정 (POST 지원)")
async def update_task_content(
    task_id: str = Path(..., description="수정할 태스크 ID"),
    payload: TaskContentUpdateRequest = ...,
):
    """태스크의 본문 내용(HTML/텍스트)을 수정합니다."""
    domain_id = resolve_domain_id(payload.domainId, task_id)
    body = {
        "content": {
            "htmlText": payload.htmlText,
            "mentionedUserIds": [],
            "inlineImages": []
        }
    }
    res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/tasks/{task_id}/content", body)
    handle_response(res)
    return {"message": "Task content updated successfully", "taskId": task_id}


@router.delete("/{task_id}", summary="태스크 삭제")
async def delete_task(
    task_id: str = Path(..., description="삭제할 태스크 ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """태스크를 영구 삭제합니다."""
    domain_id = resolve_domain_id(domain_id, task_id)
    res = await async_api_request("DELETE", f"/rd/{domain_id}/api/v1/tasks/{task_id}")
    handle_response(res)
    return {"message": "Task deleted successfully", "taskId": task_id}

