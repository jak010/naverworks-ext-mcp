from typing import Optional
from fastapi import APIRouter, Query, Path
from app.config import DEFAULT_INSTANCE_CODE
from app.core.ids import resolve_domain_id, resolve_project_rl, remember_rl, cached_rl
from app.core.client import async_api_request
from app.schemas.project import ProjectCreateRequest
from app.api.deps import handle_response

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", summary="스페이스별 프로젝트 목록 조회")
async def list_projects(
    space_id: str = Query(..., description="조회할 Space ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """특정 스페이스에 속한 활성 프로젝트 목록을 조회합니다."""
    domain_id = resolve_domain_id(domain_id, space_id)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/projects?spaceId={space_id}")
    data = handle_response(res)
    remember_rl(data)
    return data


@router.get("/{project_id}", summary="프로젝트 상세 조회")
async def get_project(
    project_id: str = Path(..., description="프로젝트 ID"),
    instance_code: Optional[str] = Query(None, description="Relay instance code (생략 시 프로젝트의 rl을 자동 사용)")
):
    """프로젝트 메타데이터, 뷰 및 커스텀 필드 상세 정보를 조회합니다."""
    instance_code = instance_code or cached_rl(project_id) or DEFAULT_INSTANCE_CODE
    res = await async_api_request("GET", f"/rl/{instance_code}/api/v1/projects/{project_id}")
    data = handle_response(res)
    remember_rl(data)
    return data


@router.post("", summary="신규 프로젝트 생성")
async def create_project(payload: ProjectCreateRequest):
    """특정 스페이스 하위에 신규 프로젝트를 생성합니다."""
    domain_id = resolve_domain_id(payload.domainId, payload.spaceId)
    body = {
        "spaceId": payload.spaceId,
        "projectName": payload.projectName,
        "projectColor": payload.projectColor,
        "projectType": payload.projectType,
        "spaceProjectParameter": None
    }
    res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/projects", body)
    data = handle_response(res)
    remember_rl(data)
    return data


@router.delete("/{project_id}", summary="프로젝트 삭제")
async def delete_project(
    project_id: str = Path(..., description="삭제할 Project ID"),
    instance_code: Optional[str] = Query(None, description="Relay instance code (생략 시 프로젝트의 rl을 자동 사용)")
):
    """프로젝트를 영구 삭제합니다."""
    instance_code = await resolve_project_rl(project_id, instance_code)
    res = await async_api_request("DELETE", f"/rl/{instance_code}/api/v1/projects/{project_id}")
    handle_response(res)
    return {"message": "Project deleted successfully", "projectId": project_id}

