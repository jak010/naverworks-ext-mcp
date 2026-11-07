"""네이버웍스 내부 API 요청 본문 생성 (MCP 도구와 REST 라우트가 공유)"""

from typing import Any, Dict, Optional


def build_task_create_payload(
    project_id: str,
    title: str,
    html_text: str = "",
    parent_task_id: Optional[str] = None,
    domain_id: str = "",
    rl: str = "",
) -> Dict[str, Any]:
    """태스크 생성 본문.

    projectTaskParameters[].taggedProjectKey 는 필수입니다 (비우면 400 INVALID_PARAMETER).
    actionUserId 는 보내지 않습니다: 실제 API 검증 결과(2026-11-07) 값을 생략하거나 임의 값을 넣어도
    생성자는 요청 쿠키의 세션 사용자로 결정되며 전달한 값은 무시됩니다.
    (과거에는 특정 사용자 ID를 기본값으로 하드코딩해 모든 익명 사용자 요청에 실어 보냈음)
    """
    return {
        "projectId": project_id,
        "title": title,
        "content": {"htmlText": html_text or "", "mentionedUserIds": [], "inlineImages": []},
        "assigneesIds": [],
        "taskStatusType": "OPEN",
        "projectTaskParameters": [
            {"taggedProjectKey": {"rl": rl, "domainId": domain_id, "projectId": project_id}}
        ],
        "parentTaskId": parent_task_id,
    }
