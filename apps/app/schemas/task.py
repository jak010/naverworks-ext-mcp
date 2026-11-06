from typing import Optional
from pydantic import BaseModel, Field


class TaskCreateRequest(BaseModel):
    projectId: str = Field(..., description="소속 프로젝트 ID", json_schema_extra={"example": "p-123456789-..."})
    title: str = Field(..., description="태스크 제목", json_schema_extra={"example": "로그인 API 구현"})
    htmlText: str = Field(default="", description="태스크 상세 본문 (HTML 또는 일반 텍스트)", json_schema_extra={"example": "<p>상세 설명</p>"})
    parentTaskId: Optional[str] = Field(default=None, description="하위 태스크인 경우 부모 태스크 ID")
    actionUserId: Optional[str] = Field(default=None, description="(사용되지 않음) 생성자는 요청 쿠키의 세션 사용자로 결정됩니다. 하위 호환을 위해서만 허용", deprecated=True)
    rl: Optional[str] = Field(default=None, description="Relay instance code")
    domainId: Optional[str] = Field(default=None, description="도메인/테넌트 ID (생략 시 기본값 사용)")


class TaskContentUpdateRequest(BaseModel):
    htmlText: str = Field(..., description="수정할 본문 내용 (HTML 또는 일반 텍스트)", json_schema_extra={"example": "<p>수정된 내용</p>"})
    domainId: Optional[str] = Field(default=None, description="도메인/테넌트 ID (생략 시 기본값 사용)")

