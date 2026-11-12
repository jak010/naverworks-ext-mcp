#!/usr/bin/env python3
"""
네이버웍스(NAVER WORKS) Service Account JWT 인증 테스트 스크립트
참고 문서: https://developers.worksmobile.com/kr/docs/auth-jwt

[인증 흐름]
1. 네이버웍스 Developer Console에서 발급받은 정보 준비:
   - Client ID
   - Client Secret
   - Service Account ID
   - Private Key (.key / .pem 파일)
2. Private Key로 전자 서명(RS256)하여 Assertion JWT 생성:
   - Header: {"alg": "RS256", "typ": "JWT"}
   - Payload: {"iss": client_id, "sub": service_account, "iat": now, "exp": now + 3600}
3. 인증 서버(https://auth.worksmobile.com/oauth2/v2.0/token)로 Access Token 발급 요청:
   - grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer
4. 발급받은 Access Token(Bearer)으로 네이버웍스 공식 API(v2.0) 호출 테스트

[실행 방법]
1) 자체 서명/기능 점검 (개발자 콘솔 정보 없을 때도 동작 확인 가능):
   ./venv/bin/python playground/test_jwt_auth.py --self-test

2) 실제 개발자 콘솔 정보로 Access Token 발급 테스트:
   ./venv/bin/python playground/test_jwt_auth.py \
       --client-id "YOUR_CLIENT_ID" \
       --client-secret "YOUR_CLIENT_SECRET" \
       --service-account "YOUR_SERVICE_ACCOUNT_ID" \
       --private-key-path "path/to/private.key" \
       --scope "user.read"
"""

import os
import sys
import time
import argparse
from typing import Dict, Any, Optional
from pprint import pprint

import jwt
import httpx
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

AUTH_TOKEN_URL = "https://auth.worksmobile.com/oauth2/v2.0/token"
API_BASE_URL = "https://www.worksapis.com/v1.0"


def generate_assertion_jwt(
    client_id: str,
    service_account: str,
    private_key_pem: str,
    exp_seconds: int = 3600,
) -> str:
    """
    네이버웍스 규격에 맞는 Assertion JWT를 생성합니다.
    - alg: RS256
    - iss: Client ID
    - sub: Service Account ID
    - iat: 발행 시각 (초 단위 Unix Timestamp)
    - exp: 만료 시각 (발행 시각으로부터 최대 3600초)
    """
    now = int(time.time())
    payload = {
        "iss": client_id,
        "sub": service_account,
        "iat": now,
        "exp": now + exp_seconds,
    }
    headers = {
        "alg": "RS256",
        "typ": "JWT",
    }

    token = jwt.encode(
        payload=payload,
        key=private_key_pem,
        algorithm="RS256",
        headers=headers,
    )
    # PyJWT 버전에 따라 str 또는 bytes 반환 대응
    return token if isinstance(token, str) else token.decode("utf-8")


def request_access_token(
    client_id: str,
    client_secret: str,
    assertion_jwt: str,
    scope: Optional[str] = None,
) -> Dict[str, Any]:
    """
    네이버웍스 인증 서버에 Access Token 발급을 요청합니다.
    POST https://auth.worksmobile.com/oauth2/v2.0/token
    """
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    }
    form_data = {
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "client_id": client_id,
        "client_secret": client_secret,
        "assertion": assertion_jwt,
    }
    if scope:
        form_data["scope"] = scope

    print("\n🌐 [인증 서버 요청 전송]")
    print(f"URL: {AUTH_TOKEN_URL}")
    print("요청 폼 파라미터 (일부 마스킹):")
    masked_data = dict(form_data)
    if client_secret:
        masked_data["client_secret"] = client_secret[:4] + "****"
    if assertion_jwt:
        masked_data["assertion"] = assertion_jwt[:20] + "...(중략)..." + assertion_jwt[-10:]
    pprint(masked_data)

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(AUTH_TOKEN_URL, headers=headers, data=form_data)
        try:
            body = resp.json()
        except Exception:
            body = resp.text

        return {
            "status_code": resp.status_code,
            "data": body,
        }


def call_sample_api(access_token: str, endpoint: str = "/users") -> Dict[str, Any]:
    """
    발급받은 Bearer Access Token으로 네이버웍스 API v2.0 호출을 테스트합니다.
    """
    url = f"{API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    print(f"\n📡 [네이버웍스 공식 API 호출 테스트: {url}]")
    with httpx.Client(timeout=15.0) as client:
        resp = client.get(url, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = resp.text
        return {
            "status_code": resp.status_code,
            "data": body,
        }


def run_self_test():
    """
    로컬에서 임의의 RSA 키쌍을 생성하여 JWT 생성 및 유효성 검증 로직이 올바른지 자체 점검합니다.
    (실제 네이버웍스 키가 없을 때도 라이브러리 및 암호화 동작을 검증)
    """
    print("=" * 70)
    print("🧪 [Self-Test] 로컬 RSA 키 생성 및 Assertion JWT 서명/검증 테스트")
    print("=" * 70)

    # 1. 2048-bit RSA 키쌍 생성
    print("1. RSA-2048 테스트용 키쌍 생성 중...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    # 2. JWT 생성
    test_client_id = "test_client_id_12345"
    test_service_account = "bot_account@serviceaccount.worksmobile.com"
    print(f"2. Assertion JWT 생성 (iss={test_client_id}, sub={test_service_account})...")

    jwt_token = generate_assertion_jwt(
        client_id=test_client_id,
        service_account=test_service_account,
        private_key_pem=private_pem,
        exp_seconds=3600,
    )
    print(f"   생성된 JWT 헤더.페이로드.서명 ({len(jwt_token)} bytes):")
    print(f"   {jwt_token[:30]}...{jwt_token[-20:]}")

    # 3. 공개키로 서명 및 페이로드 검증
    print("3. RS256 공개키로 JWT 디코딩 및 서명 검증 중...")
    decoded = jwt.decode(jwt_token, key=public_pem, algorithms=["RS256"], audience=None)
    print("   디코딩된 페이로드 검증 성공:")
    pprint(decoded)

    print("\n✅ [결과] JWT 생성 및 RS256 서명/검증 엔진이 정상적으로 준비되었습니다!")
    print("   네이버웍스 Developer Console에서 키(.key)와 Client ID를 발급받아 인자로 전달하시면")
    print("   실제 토큰 발급 테스트가 가능합니다.")


def main():
    parser = argparse.ArgumentParser(description="NAVER WORKS Service Account JWT 인증 테스트")
    parser.add_argument("--self-test", action="store_true", help="로컬 키 생성 및 JWT 서명/검증 자가 테스트")
    parser.add_argument("--client-id", default=os.getenv("WORKS_CLIENT_ID"), help="Developer Console의 Client ID")
    parser.add_argument("--client-secret", default=os.getenv("WORKS_CLIENT_SECRET"), help="Client Secret")
    parser.add_argument("--service-account", default=os.getenv("WORKS_SERVICE_ACCOUNT"), help="Service Account ID")
    parser.add_argument("--private-key-path", default=os.getenv("WORKS_PRIVATE_KEY_PATH"), help="Private Key (.key/.pem) 파일 경로")
    parser.add_argument("--scope", default=os.getenv("WORKS_SCOPE", "user.read"), help="요청할 scope (예: 'user.read bot')")

    args = parser.parse_args()

    if args.self_test or not (args.client_id and args.service_account and args.private_key_path):
        if not args.self_test:
            print("ℹ️  필수 인증 파라미터가 입력되지 않아 --self-test 모드로 실행합니다.")
            print("   (실제 인증을 진행하시려면 --client-id, --service-account, --private-key-path 등을 전달하세요)")
            print("   사용법 도움말: ./venv/bin/python playground/test_jwt_auth.py -h\n")
        run_self_test()
        return

    # 실제 키 파일 읽기
    if not os.path.exists(args.private_key_path):
        print(f"❌ 개인키 파일이 존재하지 않습니다: {args.private_key_path}")
        sys.exit(1)

    with open(args.private_key_path, "r", encoding="utf-8") as f:
        private_key_pem = f.read()

    print("=" * 70)
    print("🚀 [NAVER WORKS JWT 인증 테스트 시작]")
    print(f"• Client ID       : {args.client_id}")
    print(f"• Service Account : {args.service_account}")
    print(f"• Private Key 경로: {args.private_key_path}")
    print(f"• Scope           : {args.scope}")
    print("=" * 70)

    # 1. JWT 생성
    print("\n1. Assertion JWT (RS256) 생성 중...")
    try:
        assertion = generate_assertion_jwt(
            client_id=args.client_id,
            service_account=args.service_account,
            private_key_pem=private_key_pem,
        )
        print("   ✅ Assertion JWT 생성 완료")
    except Exception as e:
        print(f"   ❌ JWT 생성 실패: {e}")
        sys.exit(1)

    # 2. Access Token 발급 요청
    print("\n2. Access Token 발급 요청 중...")
    res = request_access_token(
        client_id=args.client_id,
        client_secret=args.client_secret or "",
        assertion_jwt=assertion,
        scope=args.scope,
    )

    print(f"\n응답 HTTP 상태 코드: {res['status_code']}")
    pprint(res["data"])

    if res["status_code"] == 200 and isinstance(res["data"], dict) and "access_token" in res["data"]:
        token = res["data"]["access_token"]
        print(f"\n🎉 [성공] Access Token 발급 완료! (유효시간: {res['data'].get('expires_in')}초)")

        # 3. 샘플 API 호출 테스트
        api_res = call_sample_api(access_token=token, endpoint="/users")
        print(f"API 응답 상태 코드: {api_res['status_code']}")
        pprint(api_res["data"])
    else:
        print("\n❌ Access Token 발급 실패. 위 에러 응답을 확인하세요.")


if __name__ == "__main__":
    main()

