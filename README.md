# NAVER WORKS Project MCP Server

AI 도구(Claude Code, Cursor, VS Code, Opencode, Claude Desktop 등)에서 **네이버웍스 Project를 대화로 다룰 수 있게 해 주는 MCP 서버**입니다. 스페이스, 프로젝트, 태스크, 태스크 댓글을 조회하고 만들고 고치고 지울 수 있습니다. 같은 기능을 REST API로도 제공합니다.

> 🚀 **처음이라면 [INSTALL.md](INSTALL.md)부터 보세요.** 공용 서버 연결, 서버 띄우기, 로컬 모드 설치를 한 장에 요약했습니다.

---

## 1. 이 프로젝트의 목적

네이버웍스 Project에는 AI 도구가 바로 쓸 수 있는 공개 API가 없습니다. 이 서버는 네이버웍스 웹이 쓰는 API를 **MCP 도구**로 감싸서, 다음과 같은 일을 대화로 할 수 있게 합니다.

- "릴리스 프로젝트에서 아직 안 끝난 태스크 정리해줘"
- "아래 회의록에서 할 일을 뽑아서 태스크로 만들어줘"
- "방금 수정한 코드 내용을 '로그인 개선' 태스크에 댓글로 남겨줘"

**설계 원칙**
- **내 권한 그대로:** 모든 요청은 요청한 사용자 본인의 네이버웍스 세션으로 실행됩니다. 웹에서 할 수 없는 일은 여기서도 할 수 없습니다. 서버는 쿠키를 저장하지 않습니다.
- **설정 최소화:** 사용자는 AI 도구에 서버 주소만 등록하고, 브라우저에서 한 번 로그인하면 됩니다. 조직 ID 같은 값은 서버가 알아서 정합니다.
- **LLM 친화적 응답:** 응답을 핵심 필드만 남긴 짧은 JSON으로 줄여 토큰 사용을 줄입니다.

---

## 2. 제공 기능

### 2.1 MCP 도구 (20개)

사용자는 평소 말하듯 요청하면 되고, AI가 알맞은 도구를 골라 실행합니다.

**스페이스**

| 도구 | 기능 | 요청 예시 |
|---|---|---|
| `list_spaces` | 내가 속한 스페이스 목록 | "내 스페이스 목록 보여줘" |
| `get_space` | 스페이스 상세와 소속 프로젝트 ID | "개발팀 스페이스 정보 알려줘" |
| `create_space` | 스페이스 생성 | "'QA팀' 스페이스 만들어줘" |
| `delete_space` | 스페이스 영구 삭제 | "QA팀 스페이스 삭제해줘" |

**프로젝트**

| 도구 | 기능 | 요청 예시 |
|---|---|---|
| `list_projects` | 스페이스 하위 프로젝트 목록 | "개발팀 스페이스 프로젝트 알려줘" |
| `get_project` | 프로젝트 상세 | "릴리스 프로젝트 정보 보여줘" |
| `create_project` | 프로젝트 생성 | "개발팀에 '사내 MCP 도입' 프로젝트 만들어줘" |
| `delete_project` | 프로젝트 영구 삭제 | "사내 MCP 도입 프로젝트 삭제해줘" |

**태스크**

| 도구 | 기능 | 요청 예시 |
|---|---|---|
| `list_tasks` | 프로젝트 태스크 목록. 기본 50개씩 보여 주고, 상태 필터와 본문 미리보기는 선택 | "릴리스 프로젝트 태스크 보여줘", "완료된 것만" |
| `get_task` | 태스크 상세(본문, 상태, 하위 태스크) | "로그인 화면 개선 태스크 자세히" |
| `create_task` | 태스크·하위 태스크 생성 | "'설치 가이드 작성' 태스크 추가해줘" |
| `update_task_content` | 태스크 본문 교체 | "그 태스크 본문을 체크리스트로 바꿔줘" |
| `delete_task` | 태스크 영구 삭제 | "그 태스크 삭제해줘" |

**태스크 댓글**

| 도구 | 기능 | 요청 예시 |
|---|---|---|
| `list_task_comments` | 댓글 목록(작성자·내용·시간). 기본 30개씩 | "그 태스크 댓글 보여줘" |
| `create_task_comment` | 댓글 작성. `parentTaskCommentId`를 주면 답글 | "'확인했습니다' 댓글 달아줘" |
| `update_task_comment` | 댓글 내용 교체 | "방금 단 댓글을 …로 고쳐줘" |
| `delete_task_comment` | 댓글 영구 삭제 | "그 댓글 지워줘" |

**인증**

| 도구 | 기능 |
|---|---|
| `get_auth_status` | 현재 연결에 로그인 정보가 전달되었는지 확인 |
| `login_naverworks` | 로그인 방법 안내. 로컬 모드에서는 브라우저를 열어 자동 로그인 |
| `set_user_cookie` | 대화 중 쿠키 등록 (SSE 연결 전용, 헤더나 OAuth를 쓸 수 없을 때만) |

> `delete_*` 도구는 **영구 삭제**이며 되돌릴 수 없습니다. 태스크의 제목·상태·담당자 변경은 아직 지원하지 않습니다.

### 2.2 서버가 자동으로 처리하는 것

- **브라우저 로그인 (MCP OAuth):** AI 도구에는 `…/mcp/rpc` 주소만 등록합니다. 처음 연결하면 로그인 페이지가 열리고, 네이버웍스 요청을 **Copy as cURL**로 붙여넣으면 쿠키와 조직 ID가 함께 설정됩니다. 세션이 만료되면 로그인 페이지가 다시 열립니다.
- **조직 ID·`rl` 자동 결정:** `domainId`(조직 ID)와 `rl`(인스턴스 코드)은 ID, 응답, 로그인 정보에서 사용자별로 알아냅니다. 사용자는 이름만 말하면 되고, 서버에 조직 값을 설정하지 않아도 여러 조직이 같은 서버를 쓸 수 있습니다.
- **토큰 절감:** 응답은 핵심 필드만 간결한 JSON으로 돌려줍니다. 목록은 페이지 단위로 나누고, HTML 본문은 텍스트로 바꾸며, 오류는 짧게 줄입니다. 태스크 100개 프로젝트를 기준으로, 기본 목록 응답(50개 표시)은 원본의 약 5%이고 100개 전체를 받아도 약 10%입니다. (만든 데이터로 측정)
- **사용자 격리와 공정성:** 요청마다 그 사용자의 쿠키만 씁니다. 사용자별·서버 전체 동시 요청 수를 제한해서, 한 사용자가 다른 사용자를 느리게 만들지 못하게 합니다.

### 2.3 그 밖의 인터페이스

| 인터페이스 | 주소 / 실행 | 용도 |
|---|---|---|
| MCP Streamable HTTP | `POST /mcp/rpc` | Claude Code, Cursor, VS Code, Opencode, Claude Desktop(mcp-remote). 브라우저 로그인 지원 |
| MCP SSE | `GET /sse`, `POST /messages` | SSE만 지원하는 클라이언트 (쿠키는 헤더로 전달) |
| MCP stdio | `apps/server.py` | 로컬 모드. AI 도구가 서버를 직접 실행 |
| REST API | `/api/v1/*`, Swagger `/docs` | 스크립트·다른 서비스 연동 ([6.4](#64-rest-api)) |
| 도구 직접 호출 | `POST /mcp/call` | MCP 클라이언트 없이 도구 실행 |
| 웹 대시보드 | `/dashboard` | 로컬 모드에서 브라우저로 조회 |
| CLI | `apps/cli.py` | 터미널에서 조회 (로컬 모드) |

---

## 3. 빠른 시작

| 상황 | 방법 | 문서 |
|---|---|---|
| 운영자가 띄운 **공용 서버**를 쓴다 | AI 도구에 `<서버 주소>/mcp/rpc` 등록 → 브라우저 로그인 | [docs/client-setup.md](docs/client-setup.md) |
| 서버를 **직접 띄워** 팀에 제공한다 | `make docker-build && make docker-up` 또는 `make run` | [5. 서버 실행](#5-서버-실행) |
| **나 혼자** Mac에서 쓴다 | `make setup` → AI 도구에 stdio로 등록 (Chrome 로그인 세션 자동 사용) | [INSTALL.md](INSTALL.md#c-로컬-모드-macos-혼자-사용) |

연결 확인: AI에게 **"네이버웍스 인증 상태 확인해줘"** → **"내 스페이스 목록 보여줘"**

---

## 4. 문서

| 문서 | 대상 | 내용 |
|---|---|---|
| [INSTALL.md](INSTALL.md) | 모두 | 설치 방식별 한 장 요약 |
| [docs/client-setup.md](docs/client-setup.md) | 사용자 | AI 도구 등록, 브라우저 로그인, 사용 예시, 문제 해결 |
| [docs/developer-guide.md](docs/developer-guide.md) | 개발자·운영자 | 인증 모드, MCP 엔드포인트, OAuth 흐름, 쿠키 전달 방식, 도구별 인자, 코드에서 호출 |
| [docs/naverworks-api-reference.md](docs/naverworks-api-reference.md) | 개발자 | 네이버웍스 Project 내부 API 명세 |

---

## 5. 서버 실행

```bash
# Docker (운영 권장, multi_user 모드, 포트 9050)
make docker-build && make docker-up
docker compose -f deploy/docker-compose.yml logs -f

# Python 직접 실행 (.venv 자동 생성, 코드 변경 시 자동 재시작)
make run                       # = deploy/run.sh

# 수동 실행
source .venv/bin/activate
python apps/main.py            # 자동 재시작: RELOAD=true python apps/main.py
```

실행 후 확인할 주소:
- 헬스체크 `http://localhost:9050/health`
- Swagger UI `http://localhost:9050/docs`, ReDoc `/redoc`
- MCP `http://localhost:9050/mcp/rpc`

외부에 공개할 때는 HTTPS 리버스 프록시 뒤에 두고 `PUBLIC_BASE_URL`을 설정하세요. ([6.2](#62-환경-변수))

---

## 6. 커스터마이징

### 6.1 인증 모드

`NAVERWORKS_AUTH_MODE`로 정합니다.

| 모드 | 용도 | 쿠키 출처 |
|---|---|---|
| `multi_user` (기본) | 여러 사용자가 쓰는 공용 서버 | **요청마다 사용자가 보낸 쿠키만** 씁니다. 출처는 OAuth 토큰, `X-Naverworks-Cookie` 헤더, `Authorization: Bearer`, `set_user_cookie` 중 하나입니다. 쿠키가 없으면 401(브라우저 로그인 유도). 서버 PC의 쿠키·파일은 쓰지 않습니다 |
| `local` | 본인 PC에서 혼자 사용 | 사용자 쿠키 → `NAVERWORKS_COOKIE` → `NAVERWORKS_COOKIE_PATH` → 로컬 쿠키 파일(Chrome에서 자동 추출) 순서로 찾습니다. `login_naverworks`가 브라우저 로그인을 실행합니다. 기본으로 `127.0.0.1`에만 열립니다 |

stdio(`apps/server.py`)와 CLI(`apps/cli.py`)는 기본이 `local`입니다.

### 6.2 환경 변수

모두 선택 사항입니다. `.env` 파일은 자동으로 읽지 않으니 셸 환경 변수나 `docker-compose.yml`의 `environment`로 지정하세요. 예시는 [deploy/.env.example](deploy/.env.example)에 있습니다.

**서버·네트워크**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `PORT` | `9050` | 서버 포트 |
| `HOST` | `multi_user`: `0.0.0.0`, `local`: `127.0.0.1` | 바인드 주소 |
| `PUBLIC_BASE_URL` | (요청 Host 기준) | 리버스 프록시 뒤의 외부 주소. OAuth 메타데이터와 로그인 주소에 쓰입니다 (예: `https://naverworks-mcp.example.com`) |
| `CORS_ALLOW_ORIGINS` | 없음 (불허) | 브라우저 교차 출처 호출을 허용할 Origin 목록 (쉼표 구분) |
| `LOCAL_ALLOWED_HOSTS` | `localhost`, `127.0.0.1`, `::1` | `local` 모드에서 추가로 허용할 Host. 그 외 Host/Origin은 403 |
| `RELOAD` | `false` | 코드 변경 시 자동 재시작 (개발용, `make run`은 켜짐) |

**인증**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NAVERWORKS_AUTH_MODE` | `multi_user` | [6.1 인증 모드](#61-인증-모드) |
| `NAVERWORKS_OAUTH_ENABLED` | `true` | 쿠키 없는 `/mcp/rpc` 요청에 401을 돌려 브라우저 로그인을 유도. `false`면 헤더 방식만 사용 |
| `NAVERWORKS_COOKIE_JAR_PATH` | `~/.config/naverworks/proj_cookies.txt` | `local` 모드의 쿠키 파일 경로 |
| `NAVERWORKS_COOKIE` / `NAVERWORKS_COOKIE_PATH` | 없음 | `local` 모드에서 쓸 쿠키 문자열 / 쿠키 파일 경로 |

**네이버웍스**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NAVERWORKS_BASE_URL` | `https://project.worksmobile.com` | 네이버웍스 Project 주소 |
| `NAVERWORKS_DOMAIN_ID` | 없음 | 조직 ID 대체값. 조직 ID는 로그인 정보 → 호출의 ID → 같은 사용자가 이전에 쓴 값 → 로그인한 웹 페이지 순서로 자동 결정합니다. 모두 실패할 때만 이 값을 씁니다. 이 값도 없으면 도구가 `DOMAIN_ID_UNKNOWN`으로 ID를 요청합니다 |
| `NAVERWORKS_INSTANCE_CODE` | `24101` | `rl` 대체값. `rl`은 응답에서 자동으로 얻고, 확인에 실패했을 때만 씁니다 |

**성능**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `NAVERWORKS_PER_USER_CONCURRENCY` | `4` | 사용자(쿠키)별 네이버웍스 동시 요청 수 |
| `NAVERWORKS_UPSTREAM_CONCURRENCY` | `25` | 서버 전체 네이버웍스 동시 요청 수 |

### 6.3 응답 크기 조정

LLM에 돌려주는 응답 크기는 `apps/app/core/mcp_spec.py` 위쪽의 상수로 조정합니다.

| 상수 | 기본값 | 의미 |
|---|---|---|
| `LIST_TASKS_DEFAULT_LIMIT` / `LIST_TASKS_MAX_LIMIT` | 50 / 200 | `list_tasks` 기본·최대 개수 |
| `COMMENTS_DEFAULT_LIMIT` / `COMMENTS_MAX_LIMIT` | 30 / 200 | `list_task_comments` 기본·최대 개수 |
| `PREVIEW_CHARS` | 80 | 태스크 본문 미리보기 길이 (`includePreview` 사용 시) |
| `ERROR_TEXT_MAX` | 500 | 오류 본문 최대 길이 |
| `CACHE_TTL` | 15초 | 같은 사용자의 같은 조회를 재사용하는 시간 (생성·수정·삭제 시 즉시 비움) |

각 목록의 어떤 필드를 남길지는 같은 파일의 `_slim_*` 함수에서 정합니다.

### 6.4 REST API

MCP와 같은 인증(헤더 `X-Naverworks-Cookie` 또는 `Authorization: Bearer`)을 씁니다. 응답은 네이버웍스 원본 그대로입니다. 전체 스키마는 `/docs`에서 볼 수 있습니다.

| Method | Endpoint | 설명 |
|---|---|---|
| `GET` | `/api/v1/spaces` | 스페이스 목록 |
| `GET` / `DELETE` | `/api/v1/spaces/{space_id}` | 스페이스 상세 / 삭제 |
| `POST` | `/api/v1/spaces` | 스페이스 생성 (`spaceName`, `spaceColor`) |
| `GET` | `/api/v1/projects?space_id=...` | 스페이스의 프로젝트 목록 |
| `GET` / `DELETE` | `/api/v1/projects/{project_id}` | 프로젝트 상세 / 삭제 |
| `POST` | `/api/v1/projects` | 프로젝트 생성 |
| `GET` | `/api/v1/tasks?project_id=...` | 프로젝트의 태스크 목록 |
| `GET` / `DELETE` | `/api/v1/tasks/{task_id}` | 태스크 상세 / 삭제 |
| `POST` | `/api/v1/tasks` | 태스크·하위 태스크 생성 |
| `PUT` | `/api/v1/tasks/{task_id}/content` | 태스크 본문 수정 |
| `GET` / `POST` | `/api/v1/tasks/{task_id}/comments` | 댓글 목록 / 작성 (`htmlText`, 선택 `parentTaskCommentId`) |
| `PUT` / `DELETE` | `/api/v1/tasks/{task_id}/comments/{comment_id}` | 댓글 수정 / 삭제 |
| `GET` | `/health`, `/` | 헬스체크, 서버 정보 |
| `POST` | `/auth/refresh-cookie` | Chrome에서 쿠키 재추출 (`local` 모드 전용) |

### 6.5 도구 추가하기

새 네이버웍스 기능을 도구로 추가하려면 다음 순서로 작업합니다. 댓글 도구 4개가 이 방식으로 추가된 예시입니다.

1. **요청 본문:** `apps/app/core/payloads.py`에 본문 생성 함수를 추가합니다. MCP와 REST가 함께 씁니다.
2. **도구 정의와 처리:** `apps/app/core/mcp_spec.py`의 `MCP_TOOLS_SPEC`에 도구 정의(이름, 설명, 입력 스키마)를 추가하고, `_execute_tool`에 처리 분기를 추가합니다.
   - 조직 ID는 `ensure_domain_id`로 정합니다.
   - `rl`은 프로젝트면 `resolve_project_rl`, 태스크면 `resolve_task_rl`로 정합니다.
   - 응답은 `_format_result`로 줄이고, 실패는 `_error_result`로 돌려줍니다.
   - 쓰기 작업이면 `invalidate_mcp_cache()`를 호출합니다.
3. **REST (선택):** `apps/app/api/v1/`에 라우트를, `apps/app/schemas/`에 요청 스키마를 추가합니다.
4. **테스트와 문서:** `tests/`에 네이버웍스를 mock으로 대체한 테스트를 추가합니다. 도구 표(이 README, `docs/developer-guide.md`)도 고칩니다.

### 6.6 프로젝트 구조

```
tpjt-naverworks-mcp/
├── apps/
│   ├── app/                        # 핵심 애플리케이션 패키지 (import 이름: app)
│   │   ├── main.py                 # FastAPI 앱, 미들웨어(요청 ID·CORS·로컬 모드 Host 검증), 로그 마스킹, 라우터
│   │   ├── config.py               # 환경 변수 설정
│   │   ├── api/
│   │   │   ├── deps.py             # 요청에서 쿠키·조직 ID 추출, 응답 처리
│   │   │   ├── mcp.py              # MCP 전송 계층 (Streamable HTTP / SSE / 직접 호출)
│   │   │   ├── oauth.py            # MCP OAuth 브라우저 로그인 (메타데이터, 로그인 페이지, 토큰)
│   │   │   ├── system.py           # 헬스체크, 대시보드, 쿠키 갱신 (local 모드)
│   │   │   └── v1/                 # REST API (spaces, projects, tasks)
│   │   ├── core/
│   │   │   ├── mcp_spec.py         # MCP 도구 정의·실행, 응답 경량화, 캐시
│   │   │   ├── ids.py              # 조직 ID(domainId)·rl 자동 결정
│   │   │   ├── client.py           # 네이버웍스 HTTP 클라이언트 (커넥션 풀, 동시성 제한)
│   │   │   ├── cookie.py           # 쿠키 우선순위, Chrome 쿠키 추출, 토큰 인코딩
│   │   │   ├── auth_context.py     # 요청별 사용자 쿠키 격리 (ContextVar)
│   │   │   └── payloads.py         # 네이버웍스 요청 본문 생성
│   │   ├── schemas/                # REST 요청 스키마
│   │   └── static/dashboard.html   # 웹 대시보드
│   ├── main.py                     # HTTP 서버 진입점
│   ├── server.py                   # stdio MCP 서버 진입점 (local 모드)
│   └── cli.py                      # 터미널 CLI (local 모드)
├── deploy/                         # setup.sh, run.sh, Dockerfile, docker-compose.yml, requirements, .env.example
├── docs/                           # 사용자·개발자 문서
├── tests/                          # pytest (네이버웍스는 mock, test_live_crud.py만 실제 API·opt-in)
├── INSTALL.md
└── Makefile                        # make help
```

### 6.7 테스트

```bash
make dev        # 가상환경 + 개발 의존성 설치
make test       # 단위·통합 테스트 (네이버웍스는 mock, 실제 요청 없음)
make lint       # pyflakes 정적 검사

# 실제 네이버웍스 대상 CRUD 테스트 (opt-in. '[MCP-TEST] <시각>' 리소스를 만들고 바로 지움)
make test-live  # 기본 쿠키 파일: ~/.config/naverworks/proj_cookies.txt (LIVE_COOKIE=경로 로 변경)
```
