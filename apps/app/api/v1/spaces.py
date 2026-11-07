from typing import Optional
from fastapi import APIRouter, Query, Path
from app.core.ids import ensure_domain_id, remember_rl
from app.core.client import async_api_request
from app.schemas.space import SpaceCreateRequest
from app.api.deps import handle_response

router = APIRouter(prefix="/spaces", tags=["Spaces"])


@router.get("", summary="스페이스 목록 조회")
async def list_spaces(
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 로그인한 계정에서 자동으로 확인)")
):
    """조직 내 전체 스페이스 목록을 조회합니다."""
    domain_id = await ensure_domain_id(domain_id)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/spaces")
    return handle_response(res)


@router.get("/{space_id}", summary="스페이스 상세 조회")
async def get_space(
    space_id: str = Path(..., description="조회할 Space ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """특정 스페이스의 상세 정보와 하위 프로젝트 목록을 조회합니다."""
    domain_id = await ensure_domain_id(domain_id, space_id)
    res = await async_api_request("GET", f"/rd/{domain_id}/api/v1/spaces/{space_id}")
    data = handle_response(res)
    remember_rl(data)
    return data


@router.post("", summary="신규 스페이스 생성")
async def create_space(payload: SpaceCreateRequest):
    """새로운 스페이스를 생성합니다."""
    domain_id = await ensure_domain_id(payload.domainId)
    body = {
        "spaceName": payload.spaceName,
        "spaceColor": payload.spaceColor,
        "spaceDescription": {
            "htmlText": "",
            "plainText": "",
            "mentionedUserIds": [],
            "inlineImages": [],
            "editorVersion": None
        }
    }
    res = await async_api_request("POST", f"/rd/{domain_id}/api/v1/spaces", body)
    return handle_response(res)


@router.delete("/{space_id}", summary="스페이스 삭제")
async def delete_space(
    space_id: str = Path(..., description="삭제할 Space ID"),
    domain_id: Optional[str] = Query(None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출)")
):
    """특정 스페이스를 영구 삭제합니다."""
    domain_id = await ensure_domain_id(domain_id, space_id)
    res = await async_api_request("DELETE", f"/rd/{domain_id}/api/v1/spaces/{space_id}")
    handle_response(res)
    return {"message": "Space deleted successfully", "spaceId": space_id}

