from typing import Optional
from pydantic import BaseModel, Field


class SpaceCreateRequest(BaseModel):
    spaceName: str = Field(..., description="스페이스 이름", json_schema_extra={"example": "신규 프로젝트 스페이스"})
    spaceColor: str = Field(default="#4694e5", description="스페이스 테마 색상 (HEX)", json_schema_extra={"example": "#4694e5"})
    domainId: Optional[str] = Field(default=None, description="도메인/테넌트 ID (생략 시 ID에서 자동 추출, 없으면 서버 기본값)")

