from typing import Optional
from fastapi import APIRouter, Query, Path
from app.core.ids import ensure_domain_id, resolve_project_rl, resolve_task_rl
from app.core.payloads import build_task_comment_payload, build_task_comment_update_payload, build_task_create_payload
from app.core.client import async_api_request
from app.schemas.task import TaskCommentCreateRequest, TaskCommentUpdateRequest, TaskCreateRequest, TaskContentUpdateRequest
from app.api.deps import handle_response

router = APIRouter(prefix="/tasks", tags=["Tasks"])


@router.get("", summary="태스크 목록 조회")
async def list_tasks(
    project_id: str = Query(..., description="소속 프로젝트 ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """특정 프로젝트에 속한 전체 태스크 목록을 조회합니다."""
    domain_id = await ensure_domain_id(domain_id, project_id)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/tasks?projectId={project_id}")
    return handle_response(res)


@router.get("/{task_id}", summary="태스크 상세 조회")
async def get_task(
    task_id: str = Path(..., description="태스크 ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """특정 태스크의 상세 정보, 본문 및 하위 작업 목록을 조회합니다."""
    domain_id = await ensure_domain_id(domain_id, task_id)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/tasks/{task_id}")
    return handle_response(res)


@router.get("/{task_id}/comments", summary="태스크 댓글 목록 조회")
async def list_task_comments(
    task_id: str = Path(..., description="태스크 ID"),
    rl: Optional[str] = Query(None, description="rl (생략 시 태스크에서 자동 확인)")
):
    """태스크에 달린 댓글 목록을 조회합니다. (네이버웍스 원본 응답)"""
    domain_id = await ensure_domain_id(None, task_id)
    rl = await resolve_task_rl(task_id, rl, domain_id)
    res = await async_api_request("GET", f"/rl/{rl}/api/v1/tasks/{task_id}/task-comments")
    return handle_response(res)


@router.post("/{task_id}/comments", summary="태스크 댓글 작성")
async def create_task_comment(
    payload: TaskCommentCreateRequest,
    task_id: str = Path(..., description="태스크 ID"),
):
    """태스크에 댓글(또는 답글)을 작성합니다. 작성자는 요청 쿠키의 사용자입니다. (네이버웍스 원본 응답)"""
    domain_id = await ensure_domain_id(None, task_id)
    rl = await resolve_task_rl(task_id, payload.rl, domain_id)
    body = build_task_comment_payload(payload.htmlText, payload.parentTaskCommentId)
    res = await async_api_request("POST", f"/rl/{rl}/api/v1/tasks/{task_id}/task-comments", body)
    return handle_response(res)


@router.put("/{task_id}/comments/{comment_id}", summary="태스크 댓글 수정")
async def update_task_comment(
    payload: TaskCommentUpdateRequest,
    task_id: str = Path(..., description="태스크 ID"),
    comment_id: str = Path(..., description="수정할 댓글 ID (tc-...)"),
):
    """태스크 댓글 내용을 새 내용으로 교체합니다."""
    domain_id = await ensure_domain_id(None, task_id)
    rl = await resolve_task_rl(task_id, payload.rl, domain_id)
    res = await async_api_request(
        "POST", f"/rl/{rl}/api/v1/tasks/{task_id}/task-comments/{comment_id}/modify-task-comment-content",
        build_task_comment_update_payload(payload.htmlText),
    )
    return handle_response(res)


@router.delete("/{task_id}/comments/{comment_id}", summary="태스크 댓글 삭제")
async def delete_task_comment(
    task_id: str = Path(..., description="태스크 ID"),
    comment_id: str = Path(..., description="삭제할 댓글 ID (tc-...)"),
    rl: Optional[str] = Query(None, description="rl (생략 시 태스크에서 자동 확인)")
):
    """태스크 댓글을 영구 삭제합니다."""
    domain_id = await ensure_domain_id(None, task_id)
    rl = await resolve_task_rl(task_id, rl, domain_id)
    res = await async_api_request("DELETE", f"/rl/{rl}/api/v1/tasks/{task_id}/task-comments/{comment_id}")
    return handle_response(res)


@router.post("", summary="신규 태스크 생성")
async def create_task(payload: TaskCreateRequest):
    """신규 태스크 또는 하위 태스크를 생성합니다."""
    domain_id = await ensure_domain_id(payload.domainId, payload.projectId, payload.parentTaskId)
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
    domain_id = await ensure_domain_id(payload.domainId, task_id)
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
    domain_id = await ensure_domain_id(domain_id, task_id)
    res = await async_api_request("DELETE", f"/rd/{domain_id}/api/v1/tasks/{task_id}")
    handle_response(res)
    return {"message": "Task deleted successfully", "taskId": task_id}

