"""네이버웍스 메일(Mail) 관련 비즈니스 로직 및 API 클라이언트 함수"""

from typing import Any, Dict, List, Optional, Union
from app.config import MAIL_BASE_URL
from app.core.client import async_api_request, api_request
from app.core.payloads import build_mail_move_payload
from app.core.ids import resolve_mail_u


async def async_move_mail(
    mail_sn_list: Union[str, List[Union[str, int]]],
    target_folder_sn: Union[str, int],
    folder_sn: Union[str, int] = 0,
    u: Optional[str] = None,
    emails: Optional[str] = "",
    auto_move: Union[str, int] = 0,
    folder_name: Optional[str] = "",
    cookie_override: Optional[str] = None,
) -> Dict[str, Any]:
    """비동기 네이버웍스 메일 이동 API 호출 (POST https://mail.worksmobile.com/json/select/move)"""
    resolved_u = resolve_mail_u(explicit=u, cookie=cookie_override)
    if not resolved_u:
        return {
            "status": 400,
            "error": "네이버웍스 메일 사용자 식별자(u)를 지정해주세요. (예: '100000000000000')"
        }

    form_data = build_mail_move_payload(
        u=resolved_u,
        mail_sn_list=mail_sn_list,
        target_folder_sn=target_folder_sn,
        folder_sn=folder_sn,
        emails=emails or "",
        auto_move=auto_move,
        folder_name=folder_name or "",
    )

    path = f"{MAIL_BASE_URL}/json/select/move"
    return await async_api_request(
        method="POST",
        path=path,
        form_data=form_data,
        cookie_override=cookie_override,
    )


def move_mail(
    mail_sn_list: Union[str, List[Union[str, int]]],
    target_folder_sn: Union[str, int],
    folder_sn: Union[str, int] = 0,
    u: Optional[str] = None,
    emails: Optional[str] = "",
    auto_move: Union[str, int] = 0,
    folder_name: Optional[str] = "",
    cookie_override: Optional[str] = None,
) -> Dict[str, Any]:
    """동기 네이버웍스 메일 이동 API 호출 (CLI 및 동기 환경용)"""
    resolved_u = resolve_mail_u(explicit=u, cookie=cookie_override)
    if not resolved_u:
        return {
            "status": 400,
            "error": "네이버웍스 메일 사용자 식별자(u)를 지정해주세요. (예: '100000000000000')"
        }

    form_data = build_mail_move_payload(
        u=resolved_u,
        mail_sn_list=mail_sn_list,
        target_folder_sn=target_folder_sn,
        folder_sn=folder_sn,
        emails=emails or "",
        auto_move=auto_move,
        folder_name=folder_name or "",
    )

    path = f"{MAIL_BASE_URL}/json/select/move"
    return api_request(
        method="POST",
        path=path,
        form_data=form_data,
        cookie_override=cookie_override,
    )

