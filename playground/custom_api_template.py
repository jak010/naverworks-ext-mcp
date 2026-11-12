#!/usr/bin/env python3
"""
새로운 네이버웍스 API 기능 추가 템플릿 (Custom API Template)

새로운 기능을 프로젝트에 추가할 때 이 코드를 참고하여 작성하세요:
1. API 호출 함수 정의 (비동기 및 동기)
2. Pydantic 요청 스키마 작성 (apps/app/schemas/ 에 추가할 내용)
3. MCP 도구 스펙 및 핸들러 작성 (apps/app/core/mcp_spec.py 에 추가할 내용)
4. FastAPI 엔드포인트 작성 (apps/app/api/v1/ 에 추가할 내용)
"""

import os
import sys
import asyncio
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

# apps 모듈 경로 설정
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
APPS_DIR = os.path.join(REPO_ROOT, "apps")
if APPS_DIR not in sys.path:
    sys.path.insert(0, APPS_DIR)

os.environ.setdefault("NAVERWORKS_AUTH_MODE", "local")

from app.core.client import async_api_request, api_request
from app.core.cookie import ensure_cookie_jar



# ==============================================================================
# 1. API 호출 코어 함수 (apps/app/core/your_feature.py 로 이동할 코드)
# ==============================================================================
async def async_call_sample_api(
    param_text: str,
    cookie_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    비동기 API 호출 함수
    """
    # [TODO] 테스트할 실제 네이버웍스 URL로 변경하세요
    endpoint = "https://project.worksmobile.com/rd/123456789/api/v1/spaces"

    return await async_api_request(
        method="GET",
        path=endpoint,
        cookie_override=cookie_override,
    )


def call_sample_api(
    param_text: str,
    cookie_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    동기 API 호출 함수 (CLI 또는 스크립트용)
    """
    endpoint = "https://project.worksmobile.com/rd/123456789/api/v1/spaces"

    return api_request(
        method="GET",
        path=endpoint,
        cookie_override=cookie_override,
    )


# ==============================================================================
# 2. Pydantic 스키마 정의 (apps/app/schemas/your_feature.py 로 이동할 코드)
# ==============================================================================
class SampleApiRequest(BaseModel):
    param_text: str = Field(..., description="테스트 파라미터 설명")
    optional_flag: Optional[bool] = Field(False, description="선택적 플래그 (기본값: False)")


# ==============================================================================
# 3. MCP 도구 스펙 (apps/app/core/mcp_spec.py 의 MCP_TOOLS_SPEC 에 추가할 코드)
# ==============================================================================
SAMPLE_MCP_TOOL_SPEC = {
    "name": "sample_api_tool",
    "description": "네이버웍스 신규 기능 API 호출 도구 설명",
    "inputSchema": {
        "type": "object",
        "properties": {
            "param_text": {
                "type": "string",
                "description": "전송할 파라미터 값"
            },
            "optional_flag": {
                "type": "boolean",
                "default": False,
                "description": "선택 플래그"
            }
        },
        "required": ["param_text"]
    }
}


# ==============================================================================
# 4. 단독 실행 테스트
# ==============================================================================
async def main():
    print("🧪 [Custom API Template] 단독 테스트 실행")
    ensure_cookie_jar()

    # 1. Pydantic 스키마 유효성 검사 테스트
    req = SampleApiRequest(param_text="test_value", optional_flag=True)
    print(f"✅ Pydantic 스키마 검증 통과: {req.model_dump()}")

    # 2. 비동기 API 호출 테스트
    print("\n🌐 API 호출 테스트 중...")
    res = await async_call_sample_api(param_text=req.param_text)
    print(f"HTTP 응답 상태 코드: {res.get('status')}")
    if res.get("status") == 200:
        print("✅ 성공 응답 수신!")
    else:
        print(f"❌ 응답 실패 또는 인증 필요: {res.get('error')}")


if __name__ == "__main__":
    asyncio.run(main())
