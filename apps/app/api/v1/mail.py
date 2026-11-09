from fastapi import APIRouter, HTTPException, Request
from app.config import MAIL_BASE_URL
from app.core.client import async_api_request
from app.core.ids import resolve_mail_u, remember_user_mail_u
from app.core.cookie import get_cookie_header
from app.schemas.mail import MailMoveRequest
from app.api.deps import handle_response

router = APIRouter(prefix="/mail", tags=["Mail"])


@router.post("/move", summary="메일 특정 메일함으로 이동")
async def move_mail(payload: MailMoveRequest, request: Request):
    """
    네이버웍스 메일을 특정 메일함으로 이동합니다.
    (POST https://mail.worksmobile.com/json/select/move)
    """
    cookie = getattr(request.state, "user_cookie", None) or get_cookie_header()
    u = resolve_mail_u(payload.u, cookie=cookie)
    if not u:
        raise HTTPException(
            status_code=400,
            detail="네이버웍스 메일 사용자 식별자(u)를 알 수 없습니다. 파라미터 u (예: '100000000000000')를 지정해 주세요."
        )

    if isinstance(payload.mailSNList, list):
        mail_sn_list = ",".join(str(item).strip() for item in payload.mailSNList if str(item).strip())
    else:
        mail_sn_list = str(payload.mailSNList).strip()

    form_payload = {
        "u": u,
        "mailSNList": mail_sn_list,
        "folderSN": str(payload.folderSN),
        "emails": str(payload.emails or ""),
        "targetFolderSN": str(payload.targetFolderSN),
        "autoMove": str(payload.autoMove if payload.autoMove is not None else 0),
        "folderName": str(payload.folderName or ""),
    }

    res = await async_api_request(
        method="POST",
        path="/json/select/move",
        base_url=MAIL_BASE_URL,
        form_data=form_payload,
        cookie_override=cookie,
    )
    if res.get("status") == 200:
        remember_user_mail_u(cookie, u)
    return handle_response(res)
