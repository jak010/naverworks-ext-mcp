# API 연동 테스트 플레이그라운드 (Playground)

네이버웍스의 새로운 내부 웹 API(메일, 캘린더, 주소록, 게시판 등)를 분석하고 테스트하기 위한 실험용 작업 공간입니다.

---

## 1. 포함된 파일

- **`test_api_runner.py`**: 터미널에서 즉시 네이버웍스 API를 호출하고 응답을 확인하는 대화형/CLI 실행 스크립트입니다.
- **`test_jwt_auth.py`**: 네이버웍스 공식 개발자 콘솔의 **Service Account JWT 인증** (Access Token 발급 및 API 호출) 테스트 스크립트입니다.
- **`custom_api_template.py`**: 새로운 API 함수를 프로젝트 코어 로직으로 개발할 때 복사해서 사용하는 기본 템플릿 코드입니다.


---

## 2. 빠른 실행 방법

가상환경 파이썬으로 스크립트를 직접 실행합니다:

```bash
# 기본 예시 실행 (메일/프로젝트 조회 테스트)
./venv/bin/python playground/test_api_runner.py

# 공식 개발자 콘솔 Service Account JWT 인증 테스트 (자가 점검)
./venv/bin/python playground/test_jwt_auth.py --self-test

# 실제 Developer Console 키로 Access Token 발급 테스트
./venv/bin/python playground/test_jwt_auth.py \
    --client-id "YOUR_CLIENT_ID" \
    --client-secret "YOUR_CLIENT_SECRET" \
    --service-account "YOUR_SERVICE_ACCOUNT_ID" \
    --private-key-path "path/to/private.key" \
    --scope "user.read"

# 또는 커스텀 템플릿 실행
./venv/bin/python playground/custom_api_template.py
```


---

## 3. 새로운 API 연동 순서 가이드

1. **브라우저에서 API 확인**:
   - 크롬 브라우저에서 네이버웍스 웹에 접속하고 개발자 도구(F12)의 **Network** 탭을 엽니다.
   - 원하는 기능(예: 캘린더 일정 등록, 메일 조회, 게시글 작성 등)을 직접 수행합니다.
   - 호출된 네트워크 요청의 **URL**, **Method**(GET/POST), **Request Payload**(JSON 또는 Form urlencoded), **헤더**를 확인합니다.

2. **`playground/test_api_runner.py`로 사전 테스트**:
   - URL과 전송 데이터를 수정하여 응답이 정상(200 OK)으로 오는지 확인합니다.

3. **프로젝트 정식 반영**:
   - `apps/app/schemas/`: 요청/응답 Pydantic 스키마 정의
   - `apps/app/core/`: 비즈니스 로직 및 API 호출 함수 작성
   - `apps/app/api/v1/`: FastAPI REST 엔드포인트 등록
   - `apps/app/core/mcp_spec.py`: AI/LLM용 MCP 도구(Tool) 등록
   - `tests/`: 단위 테스트 작성

