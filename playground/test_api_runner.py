#!/usr/bin/env python3
"""
NAVER WORKS 새 API 연동 테스트 스크립트

사용법:
    ./venv/bin/python playground/test_api_runner.py
"""

import os
import sys
import asyncio
from pprint import pprint


# 1. apps 모듈 경로 추가 및 local 모드 설정
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
APPS_DIR = os.path.join(REPO_ROOT, "apps")
if APPS_DIR not in sys.path:
    sys.path.insert(0, APPS_DIR)

# 로컬 쿠키 파일(~/.config/naverworks/proj_cookies.txt) 자동 활용
os.environ.setdefault("NAVERWORKS_AUTH_MODE", "local")

from app.core.cookie import ensure_cookie_jar, get_cookie_header, is_cookie_valid
from app.core.client import api_request, async_api_request


def print_section(title: str):
    print("\n" + "=" * 70)
    print(f"📌 {title}")
    print("=" * 70)


def check_auth():
    """인증 쿠키 유효성 검사"""
    ensure_cookie_jar()
    cookie = get_cookie_header()
    if not is_cookie_valid():
        print("❌ 유효한 네이버웍스 쿠키를 찾을 수 없습니다.")
        print("   Chrome 브라우저에서 네이버웍스에 로그인한 후 아래 명령어로 쿠키를 갱신하세요:")
        print("   ./venv/bin/python apps/cli.py refresh-cookie")
        return False
    print(f"✅ 인증 쿠키 확인 완료 (쿠키 길이: {len(cookie)} 글자)")
    return True


# ------------------------------------------------------------------------------
# 1. GET 요청 테스트 예시
# ------------------------------------------------------------------------------
def test_get_request():
    print_section("1. GET 요청 테스트 (스페이스 목록 조회)")

    # 상대 경로 사용 시 BASE_URL(https://project.worksmobile.com) 뒤에 붙습니다.
    # 전체 URL (예: https://mail.worksmobile.com/...)을 직접 지정할 수도 있습니다.
    path = "/rd/123456789/api/v1/spaces"
    print(f"요청 URL: {path} (GET)")

    res = api_request(method="GET", path=path)
    print(f"응답 상태 코드: {res.get('status')}")
    if res.get("status") == 200:
        print("응답 데이터 요약:")
        data = res.get("data")
        pprint(data if isinstance(data, list) else list(data.keys()) if isinstance(data, dict) else data)
    else:
        print(f"오류 내용: {res.get('error')}")


# ------------------------------------------------------------------------------
# 2. POST (JSON 바디) 요청 테스트 예시
# ------------------------------------------------------------------------------
async def test_post_json_request():
    print_section("2. POST (JSON) 요청 테스트 (비동기 호출 구조 확인)")

    url = "https://project.worksmobile.com/rd/123456789/api/v1/spaces"
    payload = {
        "spaceName": "[테스트] 신규 스페이스",
        "spaceColor": "#4694e5",
    }
    print(f"요청 URL: {url} (POST JSON)")
    print("요청 페이로드:")
    pprint(payload)
    print("비동기 API 요청 함수 참조: async_api_request 사용 가능")
    _ = async_api_request



# ------------------------------------------------------------------------------
# 3. POST (Form URL-Encoded) 요청 테스트 예시 (예: 메일 이동 API)
# ------------------------------------------------------------------------------
async def test_post_form_request():
    print_section("3. POST (Form urlencoded) 요청 테스트 (메일 이동 API 구조)")

    # 메일 서비스의 내부 API URL
    url = "https://mail.worksmobile.com/json/select/move"
    form_data = {
        "u": "100000000000000",          # 사용자 번호 (userNo)
        "mailSNList": "c203",             # 대상 메일 식별자
        "folderSN": "0",                  # 현재 메일함 (0 = 받은편지함)
        "targetFolderSN": "101",          # 이동할 메일함 번호
        "autoMove": "0",
        "emails": "",
        "folderName": "",
    }
    print(f"요청 URL: {url} (POST x-www-form-urlencoded)")
    print("요청 폼 데이터:")
    pprint(form_data)

    print("\n⚠️  실제 요청 전송 코드 예시: await async_api_request('POST', url, form_data=form_data)")


# ------------------------------------------------------------------------------
# 4. 나만의 신규 API 빠른 테스트 함수
# ------------------------------------------------------------------------------
async def test_custom_api():
    print_section("4. 신규 API 연동 실습 영역")
    print("💡 브라우저 개발자 도구(F12) Network 탭에서 복사한 정보를 아래에 넣고 실행하세요.")

    # [TODO] 테스트하려는 API의 URL과 파라미터로 수정하세요
    target_url = "https://project.worksmobile.com/rd/123456789/api/v1/spaces"
    method = "GET"
    print(f"실습 대상 엔드포인트: [{method}] {target_url}")

    # 실제 요청 실행 예시:
    # res = await async_api_request(method=method, path=target_url)
    # print(f"응답 결과 ({res.get('status')}):")
    # pprint(res.get('data'))



async def main():
    print("🚀 네이버웍스 API 연동 테스트 플레이그라운드 시작")
    if not check_auth():
        return

    # 1. GET 테스트
    test_get_request()

    # 2. POST (JSON) 테스트
    await test_post_json_request()

    # 3. POST (Form urlencoded) 테스트
    await test_post_form_request()

    # 4. 커스텀 API 실습
    await test_custom_api()

    print("\n✨ 모든 테스트 시나리오가 완료되었습니다.")


if __name__ == "__main__":
    asyncio.run(main())
