from typing import Optional
from pydantic import BaseModel, Field


class ProjectCreateRequest(BaseModel):
    spaceId: str = Field(..., description="상위 스페이스 ID", json_schema_extra={"example": "s-300098158-..."})
    projectName: str = Field(..., description="프로젝트 이름", json_schema_extra={"example": "신규 서비스 개발"})
    projectColor: str = Field(default="#ed7200", description="프로젝트 색상 (HEX)", json_schema_extra={"example": "#ed7200"})
    projectType: str = Field(default="OPEN", description="프로젝트 유형 (OPEN 또는 CONFIDENTIAL)", json_schema_extra={"example": "OPEN"})
    domainId: Optional[str] = Field(default=None, description="도메인/테넌트 ID (생략 시 기본값 사용)")

