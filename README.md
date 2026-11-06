# NAVER WORKS Custom API & MCP Server (FastAPI)

네이버웍스 Project/Spaces/Tasks 웹 API 기능을 손쉽게 제어할 수 있는 **FastAPI 기반 REST API 및 MCP 서버**입니다. 대화형 Swagger 문서(`/docs`), 웹 대시보드(`/dashboard`, local 모드), MCP(2024-11-05 HTTP+SSE 전송 / stdio)를 지원합니다.

> 👤 **사용자 PC에 MCP를 연결하는 방법(쿠키 복사 → AI 도구 등록)은 [docs/client-setup](docs/client-setup/README.md)을 참고하세요.**
>
> 📖 **Claude Desktop, Cursor, Antigravity 등 LLM 연동 방법은 [docs/llm-integration-guide.md](docs/llm-integration-guide.md)를 참고하세요.**

---

## 1. 주요 특징
- **FastAPI RESTful API**: 스페이스, 프로젝트, 태스크의 생성/조회/수정/삭제를 위한 깔끔한 REST API 엔드포인트 제공
- **Swagger UI (`/docs`) 자동 제공**: 브라우저에서 대화형으로 API 테스트 및 스키마 확인 가능
- **쿠키 자동 복호화 & 세션 갱신**: macOS Chrome 키체인(`Chrome Safe Storage`)을 통한 세션 자동 추출 및 만료 시 자동 갱신
- **MCP (Model Context Protocol) 호환**:
  - HTTP JSON-RPC (`/mcp/rpc`)
  - 도구 직접 호출 (`/mcp/call`)
  - 도구 명세 조회 (`/mcp/tools`)
  - 원격 SSE 스트리밍 (`/sse`, `/messages`)

---

## 2. 프로젝트 패키지 구조

FastAPI 표준 계층형 아키텍처(Layered / Modular Architecture)로 모듈과 관심사를 명확히 분리하여 설계되었습니다:

```
tpjt-naverworks-mcp/
├── apps/                           # 기능 및 서비스 제공 코드
│   ├── app/                        # 핵심 애플리케이션 패키지 (import 이름: app)
│   │   ├── main.py                 # FastAPI 인스턴스, 미들웨어(요청 ID·CORS·로컬 모드 Host/Origin 검증), 로그 마스킹, 라우터 통합
│   │   ├── config.py               # 환경 변수 및 설정 (인증 모드, 바인드 호스트, CORS, 도메인 ID 등)
│   │   ├── api/                    # API 엔드포인트 라우터 계층
│   │   │   ├── deps.py             # 공통 의존성 (요청 쿠키 추출·바인딩, 응답 처리)
│   │   │   ├── system.py           # Root, Health, Dashboard, 쿠키 갱신/브라우저 로그인 (local 모드 전용)
│   │   │   ├── mcp.py              # MCP 전송 계층 (SSE / Messages / JSON-RPC / Tools), SSE 세션 관리
│   │   │   └── v1/                 # 네이버웍스 REST API (spaces.py, projects.py, tasks.py)
│   │   ├── core/                   # 코어 인프라 및 통신 계층
│   │   │   ├── auth_context.py     # 요청/세션별 사용자 쿠키 격리 (ContextVar)
│   │   │   ├── client.py           # 네이버웍스 HTTP 클라이언트 (커넥션 풀, 전역/사용자별 동시성 제한)
│   │   │   ├── cookie.py           # 쿠키 결정 우선순위, Chrome Safe Storage 쿠키 추출 (local 모드)
│   │   │   ├── mcp_spec.py         # MCP 도구 명세 및 디스패처, 응답 경량화, 사용자별 캐시
│   │   │   └── payloads.py         # 네이버웍스 요청 본문 생성 (MCP·REST 공용)
│   │   ├── schemas/                # Pydantic 요청/응답 스키마
│   │   └── static/dashboard.html   # 웹 대시보드 (/dashboard)
│   ├── main.py                     # HTTP 서버 진입점 (uvicorn 실행 래퍼)
│   ├── server.py                   # stdio MCP 서버 진입점 (local 모드 기본)
│   └── cli.py                      # 터미널용 관리 CLI (local 모드 기본)
├── deploy/                         # 설치·실행·배포
│   ├── setup.sh                    # 원클릭 설치 (가상환경, Chrome 쿠키 연동, API 연결 확인)
│   ├── run.sh                      # 개발용 간편 실행 (자동 재시작)
│   ├── Dockerfile                  # 이미지 빌드 (컨텍스트: 저장소 루트)
│   ├── Dockerfile.dockerignore     # 이미지 제외 목록 (BuildKit)
│   ├── docker-compose.yml          # multi_user 모드 서비스 실행
│   ├── requirements.txt            # 실행 의존성
│   ├── requirements-dev.txt        # 개발·테스트 의존성
│   └── .env.example                # 환경 변수 예시
├── docs/                           # 문서 (사용자 설정 가이드, LLM 연동 가이드, 내부 API 명세)
├── tests/                          # Pytest 테스트 (네이버웍스 mock, test_live_crud.py만 실제 API·opt-in)
├── Makefile                        # 자주 쓰는 명령 모음 (make help)
├── pytest.ini / .python-version    # 테스트 설정 / Python 버전(3.13)
└── README.md
```

---

## 3. 설치 및 세팅 (원클릭)

쿠키 파일이 없거나 처음 프로젝트를 시작할 때 아래 명령을 실행하면, **가상환경 설치부터 브라우저 쿠키 연동 및 API 연결 테스트까지 자동으로 진행**됩니다:

```bash
deploy/setup.sh      # 또는 make setup
```

> **쿠키가 없는 경우 동작 흐름**:
> 1. Chrome 키체인에서 네이버웍스 세션을 자동 추출합니다.
> 2. 로그인이 안 되어 있을 경우 **자동으로 Chrome 브라우저를 띄워 네이버웍스 로그인 페이지로 안내**합니다.
> 3. 로그인 완료 후 엔터를 누르면 쿠키를 추출하여 `~/.config/naverworks/proj_cookies.txt`에 저장하고 연결을 검증합니다.

---

## 4. 서버 실행 방법

### 방법 1. 간편 실행 스크립트 또는 Make 사용
```bash
deploy/run.sh
# 또는 make 사용
make run
```

### 방법 2. 가상환경 및 수동 실행
```bash
source .venv/bin/activate
python apps/main.py            # 개발 중 자동 재시작: RELOAD=true python apps/main.py
```

서버가 실행되면 브라우저에서 아래 주소로 접속할 수 있습니다:
- **Swagger UI**: [http://localhost:9050/docs](http://localhost:9050/docs)
- **ReDoc**: [http://localhost:9050/redoc](http://localhost:9050/redoc)
- **OpenAPI Schema**: [http://localhost:9050/openapi.json](http://localhost:9050/openapi.json)
- **웹 대시보드**: [http://localhost:9050/dashboard](http://localhost:9050/dashboard)

---

## 4. API 엔드포인트 요약

### 🌐 시스템 & 인증
| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/` | 서버 상태 및 문서 링크 확인 |
| `GET` | `/health` | 헬스체크 |
| `POST` | `/auth/refresh-cookie` | Chrome 키체인에서 네이버웍스 쿠키 수동 재추출 (`local` 모드 전용, 그 외 403) |

### 📁 스페이스 (Spaces)
| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/api/v1/spaces` | 전체 스페이스 목록 조회 |
| `GET` | `/api/v1/spaces/{space_id}` | 특정 스페이스 상세 정보 조회 |
| `POST` | `/api/v1/spaces` | 신규 스페이스 생성 (`spaceName`, `spaceColor`) |
| `DELETE`| `/api/v1/spaces/{space_id}` | 스페이스 영구 삭제 |

### 🚀 프로젝트 (Projects)
| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/api/v1/projects?space_id=...` | 특정 스페이스에 속한 활성 프로젝트 목록 조회 |
| `GET` | `/api/v1/projects/{project_id}` | 프로젝트 상세 정보, 뷰, 커스텀 필드 조회 |
| `POST` | `/api/v1/projects` | 특정 스페이스 하위에 신규 프로젝트 생성 |
| `DELETE`| `/api/v1/projects/{project_id}` | 프로젝트 영구 삭제 |

### ✅ 태스크 (Tasks)
| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/api/v1/tasks?project_id=...` | 특정 프로젝트 소속 태스크 목록 조회 |
| `GET` | `/api/v1/tasks/{task_id}` | 태스크 상세 정보 및 하위 태스크 목록 조회 |
| `POST` | `/api/v1/tasks` | 신규 태스크 또는 하위 태스크 생성 |
| `PUT` | `/api/v1/tasks/{task_id}/content` | 태스크 본문 내용 수정 (HTML/Text) |
| `DELETE`| `/api/v1/tasks/{task_id}` | 태스크 영구 삭제 |

### 🤖 MCP 호환 인터페이스
| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/sse` | MCP SSE (Server-Sent Events) 스트림 연결 |
| `POST` | `/messages` | SSE 세션 기반 JSON-RPC 메시지 전송 |
| `GET` | `/mcp/tools` | MCP 도구 명세 조회 (두 모드 모두 16개, `login_naverworks` 동작만 다름) |
| `POST` | `/mcp/call` | 특정 도구 직접 실행 (`name`, `arguments`) |
| `POST` | `/mcp/rpc` | 표준 MCP JSON-RPC 2.0 요청 처리 |

---

## 5. 환경 변수 설정 (선택 사항)

필요에 따라 `.env` 파일 또는 환경 변수를 지정하여 실행할 수 있습니다:
- `PORT`: 서버 포트 (기본값: `9050`)
- `NAVERWORKS_OAUTH_ENABLED`: 쿠키 없는 `/mcp/rpc` 요청에 401을 돌려 MCP 클라이언트의 브라우저 로그인(OAuth)을 유도 (기본값: `true`)
- `PUBLIC_BASE_URL`: OAuth 메타데이터에 쓸 외부 주소 (리버스 프록시 뒤에서 지정, 기본값: 요청 Host 기준)
- `HOST`: 바인드 호스트 (기본값: `multi_user` 모드 `0.0.0.0`, `local` 모드 `127.0.0.1`)
- `CORS_ALLOW_ORIGINS`: 브라우저 교차 출처 호출을 허용할 Origin 목록 (쉼표 구분, 기본값: 없음 = 불허)
- `LOCAL_ALLOWED_HOSTS`: `local` 모드에서 추가로 허용할 Host 이름 (기본: `localhost`, `127.0.0.1`, `::1`). 그 외 Host/Origin 요청은 403
- `NAVERWORKS_PER_USER_CONCURRENCY`: 사용자(쿠키)별 네이버웍스 동시 요청 수 (기본값: `4`)
- `NAVERWORKS_UPSTREAM_CONCURRENCY`: 서버 전체 네이버웍스 동시 요청 수 (기본값: `25`)
- `NAVERWORKS_DOMAIN_ID`: 기본 도메인 ID (기본값: `123456789`)
- `NAVERWORKS_INSTANCE_CODE`: 기본 릴레이 코드 (기본값: `24101`)
- `NAVERWORKS_COOKIE_JAR_PATH`: 로컬 쿠키 파일 경로 (기본값: `~/.config/naverworks/proj_cookies.txt`)
- `NAVERWORKS_AUTH_MODE`: 인증 모드 (기본값: `multi_user`, stdio `apps/server.py`/`apps/cli.py`는 `local`)

| 모드 | 용도 | 쿠키 출처 |
|---|---|---|
| `multi_user` (기본) | 익명 다중 사용자 서비스 | **요청/세션별 사용자 쿠키만** (`X-Naverworks-Cookie`, `Authorization: Bearer`, `set_user_cookie`). 쿠키 미제공 시 401. 서버 환경 변수·로컬 쿠키 파일·쿠키 파일 경로 입력·브라우저 로그인 사용 안 함 |
| `local` | 본인 PC 단독 사용 | 사용자 쿠키 → `NAVERWORKS_COOKIE` → `NAVERWORKS_COOKIE_PATH` → 로컬 쿠키 파일. 파일 경로 헤더 허용, `login_naverworks`가 브라우저 로그인 실행 (multi_user에서는 수동 로그인 안내만 반환) |

REST API(`/api/v1/*`)도 MCP와 같은 헤더로 사용자 쿠키를 받습니다. 접근 로그의 `?cookie=` 쿼리 값은 `***`로 가려집니다.

---

### 테스트

```bash
make dev                      # 가상환경 + 개발 의존성 설치 (deploy/setup.sh 를 실행했다면 생략)
make test                     # 단위/통합 테스트 (네이버웍스는 mock 처리, 실제 요청 없음)
make lint                     # pyflakes 정적 검사

# 실제 네이버웍스 대상 CRUD 통합 테스트 (opt-in, '[MCP-TEST] <시각>' 리소스를 생성 후 즉시 삭제)
make test-live                # 기본 쿠키 파일: ~/.config/naverworks/proj_cookies.txt (LIVE_COOKIE=경로 로 변경)
```

> **태스크 생성자**: 태스크는 항상 요청 쿠키의 사용자 명의로 생성됩니다. 네이버웍스 API는 `actionUserId` 값을 무시하므로 서버는 이 값을 보내지 않습니다.

---

## 6. Docker 실행 방법

```bash
# Docker Compose로 실행
make docker-up            # = docker compose -f deploy/docker-compose.yml up -d

# 로그 확인
docker compose -f deploy/docker-compose.yml logs -f
```

---

## 7. AI 도구(MCP 클라이언트) 연동

각 사용자는 자신의 네이버웍스 쿠키를 `X-Naverworks-Cookie` 헤더로 전달해 연결합니다. 사용자 PC에는 Python이나 이 저장소가 필요 없습니다.

- **사용자 설정 가이드 (최종 체크리스트 포함)**: [docs/client-setup](docs/client-setup/README.md) — 쿠키 복사, Claude Desktop·Claude Code·Cursor·VS Code·Opencode 설정, 보안 수칙
- **`url` + `headers` 형식 예시** (Cursor 등): [docs/client-setup/mcp_config_example.json](docs/client-setup/mcp_config_example.json) — Claude Desktop은 이 형식을 지원하지 않으므로 `mcp-remote`를 사용합니다 ([설정 방법](docs/client-setup/02-client-config.md#claude-desktop))
- **그 밖의 클라이언트, 쿠키 전달 방식 상세, 코드에서 직접 호출**: [docs/llm-integration-guide.md](docs/llm-integration-guide.md)
