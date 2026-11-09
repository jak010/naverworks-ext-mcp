from typing import Optional, List, Union
from pydantic import BaseModel, Field


class MailMoveRequest(BaseModel):
    mailSNList: Union[str, List[Union[str, int]]] = Field(
        ...,
        description="이동할 메일 일련번호 목록 (예: 'c203' 또는 ['c203', 'c204'])"
    )
    targetFolderSN: Union[str, int] = Field(
        ...,
        description="이동할 대상 메일함 번호 (예: 101 또는 '101')"
    )
    folderSN: Union[str, int] = Field(
        0,
        description="현재 메일함 번호 (기본값: 0 - 받은편지함)"
    )
    u: Optional[str] = Field(
        None,
        description="네이버웍스 메일 사용자 식별자 (예: '100000000000000'). 생략 시 쿠키/세션에서 자동 조회"
    )
    emails: Optional[str] = Field(
        "",
        description="이메일 주소 (기본값: '')"
    )
    autoMove: Optional[Union[str, int]] = Field(
        0,
        description="자동 이동 여부 (기본값: 0)"
    )
    folderName: Optional[str] = Field(
        "",
        description="메일함 이름 (기본값: '')"
    )
