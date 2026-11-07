# LLM 연동 가이드 (개발자·운영자용)

NAVER WORKS MCP 서버를 **실행**하고, MCP 클라이언트·에이전트 프레임워크·직접 작성한 코드에서 **연동**하는 방법을 설명합니다.

> 👤 **일반 사용자**가 내 PC의 AI 도구(Claude Desktop, Claude Code, Cursor, VS Code, Opencode)를 공용 서버에 연결하는 방법은 [client-setup](client-setup.md)을 보세요.

---

## 1. 서버 실행

### 1.1 인증 모드

| 모드 | 기본으로 쓰는 곳 | 쿠키 출처 |
|---|---|---|
| `multi_user` | HTTP 서버(`apps/main.py`, `make run`, Docker) | **요청/세션별 사용자 쿠키만** 사용. 쿠키가 없으면 `/mcp/rpc`는 HTTP 401(OAuth 로그인 유도), 그 밖의 경로는 `UNAUTHORIZED` |
| `local` | stdio 서버(`apps/server.py`), CLI(`apps/cli.py`) | 사용자 쿠키 → `NAVERWORKS_COOKIE` → `NAVERWORKS_COOKIE_PATH` → 로컬 쿠키 파일 `~/.config/naverworks/proj_cookies.txt` |

`NAVERWORKS_AUTH_MODE` 환경 변수로 바꿀 수 있습니다. 브라우저 로그인 관련 설정은 `NAVERWORKS_OAUTH_ENABLED`(기본 `true`)와 `PUBLIC_BASE_URL`입니다 ([2.1 OAuth](#21-브라우저-로그인-oauth)). 자세한 설정 항목은 [README의 환경 변수](../README.md#62-환경-변수)를 참고하세요.

### 1.2 설치

```bash
make dev             # 가상환경(.venv) + 의존성 설치
# macOS에서 본인 쿠키까지 연동하려면 (Chrome 로그인 세션에서 쿠키 추출 → API 연결 확인):
make setup           # = deploy/setup.sh
```

### 1.3 실행

```bash
make run             # 개발용 HTTP 서버 (multi_user, 자동 재시작, http://localhost:9050)
NAVERWORKS_AUTH_MODE=local make run    # 본인 PC 단독 사용 (127.0.0.1 에만 바인드, 로컬 쿠키 파일 사용)
make docker-up       # 운영: Docker Compose (multi_user) — deploy/docker-compose.yml
```

> 운영 환경에서는 반드시 **HTTPS 리버스 프록시** 뒤에 두세요. 서버 자체는 TLS를 제공하지 않으며, 사용자 쿠키가 요청 헤더로 오갑니다.
> 프록시 뒤에서는 `PUBLIC_BASE_URL=https://naverworks-mcp.example.com` 을 지정하세요. OAuth 메타데이터의 주소가 이 값으로 만들어집니다. (미지정 시 `X-Forwarded-Proto`/`X-Forwarded-Host` 또는 요청 Host 기준)

### 1.4 확인

| 주소 | 설명 |
|---|---|
| `GET /health` | 헬스체크 (`{"status":"ok"}`) |
| `GET /docs` | Swagger UI. `multi_user` 모드에서 API를 시험하려면 요청에 `X-Naverworks-Cookie` 헤더가 필요합니다. |
| `GET /dashboard` | 웹 대시보드. 브라우저가 쿠키 헤더를 보내지 않으므로 **`local` 모드에서만** 데이터가 보입니다. (`쿠키 갱신` 버튼도 local 전용) |

---

## 2. MCP 엔드포인트

| Method | 경로 | 설명 |
|---|---|---|
| `GET` | `/sse` | MCP SSE 스트림 (MCP 2024-11-05 HTTP+SSE 전송). 첫 이벤트 `event: endpoint` 로 메시지 전송 주소를 알려 줌 |
| `POST` | `/messages?session_id=…` | SSE 세션으로 JSON-RPC 메시지 전송. **`202 Accepted`만 반환**하고 응답은 SSE 스트림의 `event: message` 로 전달 |
| `POST` | `/mcp/rpc` | 단발성 JSON-RPC 2.0 (`initialize`, `tools/list`, `tools/call`, `ping`) — HTTP 응답 본문으로 결과 반환. Streamable HTTP만 지원하는 클라이언트(Opencode 등)는 이 주소로 연결 (`GET`은 405로 응답, 서버 → 클라이언트 알림 스트림 없음). 쿠키가 없거나 네이버웍스가 401을 돌려주면 **HTTP 401 + `WWW-Authenticate`** 로 응답 ([2.1](#21-브라우저-로그인-oauth)) |
| `POST` | `/mcp/call` | 도구 직접 실행 `{"name": "...", "arguments": {...}}` |
| `GET` | `/mcp/tools` | 도구 명세 목록 (현재 인증 모드에서 사용 가능한 도구만) |

### 2.1 브라우저 로그인 (OAuth)

`/mcp/rpc`는 MCP 표준 인가 흐름(OAuth 2.1 + PKCE)을 지원합니다. 서버가 자체 인가 서버 역할을 하며, 네이버웍스 쿠키를 access token으로 감싸 발급합니다. 토큰 형식은 `nwt_` + base64url(JSON `{c: 쿠키, d: 조직 ID}`)이고 패딩은 없습니다. 조직 ID가 없으면 `nwc_` + base64url(쿠키) 형식입니다. 쿠키 원문의 공백과 `;`이 Bearer 토큰 형식(RFC 6750)에 맞지 않기 때문입니다.

```
클라이언트 ── POST /mcp/rpc (쿠키 없음) ──▶ 401, WWW-Authenticate: Bearer resource_metadata=".../.well-known/oauth-protected-resource"
          ── GET  /.well-known/oauth-protected-resource   → authorization_servers
          ── GET  /.well-known/oauth-authorization-server → 각 엔드포인트
          ── POST /oauth/register                          → client_id (동적 등록, 공개 클라이언트)
브라우저   ── GET  /oauth/authorize?...&code_challenge=…    → 로그인 페이지 (네이버웍스 열기 + 쿠키 붙여넣기)
          ── POST /oauth/authorize (Copy as cURL)          → 쿠키·조직 ID 추출 → 네이버웍스 API로 검증 → redirect_uri?code=…&state=…
클라이언트 ── POST /oauth/token (code, code_verifier)       → {"access_token": "nwt_<base64url({c: 쿠키, d: 조직 ID})>", "token_type": "Bearer"}
          ── POST /mcp/rpc, Authorization: Bearer nwc_…    → 서버가 쿠키로 복원해 처리
```

| Method | 경로 | 설명 |
|---|---|---|
| `GET` | `/.well-known/oauth-protected-resource` | 보호 리소스 메타데이터 (RFC 9728) |
| `GET` | `/.well-known/oauth-authorization-server` | 인가 서버 메타데이터 (RFC 8414). `/.well-known/openid-configuration`도 같은 내용 |
| `POST` | `/oauth/register` | 동적 클라이언트 등록 (RFC 7591). 저장하지 않음 |
| `GET`/`POST` | `/oauth/authorize` | 로그인 페이지 / 쿠키 제출. `response_type=code`, PKCE `S256` 필수 |
| `POST` | `/oauth/token` | `grant_type=authorization_code`만 지원 (refresh token 없음 → 만료 시 재로그인) |

- 네이버웍스 쿠키는 `worksmobile.com`의 HttpOnly 쿠키라 다른 도메인의 이 서버가 읽을 수 없습니다. 그래서 로그인 페이지에서 사용자가 쿠키를 한 번 붙여넣습니다.
- 서버는 쿠키를 저장하지 않습니다. 인가 코드(5분, 1회용)만 **프로세스 메모리**에 둡니다. 따라서 워커/인스턴스를 여러 개 띄우면 `/oauth/authorize`와 `/oauth/token`이 다른 프로세스로 갈 때 로그인에 실패합니다. 단일 프로세스로 운영하거나 고정 세션(sticky session)을 사용하세요.
- `redirect_uri`는 `https://` 또는 `http://localhost`·`127.0.0.1`·`[::1]`만 허용합니다.
- `X-Naverworks-Cookie` 헤더가 함께 오면 헤더가 Bearer 토큰보다 우선합니다.
- 끄려면 `NAVERWORKS_OAUTH_ENABLED=false` (쿠키 없는 `/mcp/rpc` 요청도 200으로 처리하고 도구가 `UNAUTHORIZED`를 반환하는 이전 동작).
- `local` 모드에서는 로컬 쿠키 파일 등 쿠키를 하나도 찾지 못한 경우에만 401을 돌려줍니다.

REST API(`/api/v1/spaces`, `/api/v1/projects`, `/api/v1/tasks`)도 같은 쿠키 헤더로 인증합니다. 전체 목록은 [README의 API 엔드포인트 요약](../README.md#64-rest-api)을 참고하세요.

---

## 3. 쿠키 전달 방법

| 방법 | 형식 | 유지 범위 | 모드 |
|---|---|---|---|
| **OAuth 브라우저 로그인** | `Authorization: Bearer nwc_…` (클라이언트가 자동 관리) | 클라이언트가 토큰을 저장하는 동안 (`/mcp/rpc` 전용) | 모두 |
| **헤더 (권장)** | `X-Naverworks-Cookie: WORKS_SES=...; ...` 또는 `Authorization: Bearer <쿠키 문자열>` | SSE: 핸드셰이크 때 보낸 쿠키가 세션 종료까지 유지. 메시지마다 헤더를 보내면 그 메시지에만 우선 적용 | 모두 |
| `set_user_cookie` 도구 | `{"cookie": "WORKS_SES=..."}` | **현재 SSE 세션에만** 유지. `/mcp/rpc`·`/mcp/call`에서는 그 요청이 끝나면 사라짐 | 모두 |
| 쿠키 파일 경로 | `X-Naverworks-Cookie-Path` 헤더, `?cookie_path=`, `set_user_cookie`의 `cookiePath` | 경로는 **서버 PC의 파일**을 가리킴 | `local` 전용 (multi_user에서는 무시·거부) |
| 쿼리 `?cookie=` | `/sse?cookie=...` | SSE 세션 | 모두 (헤더를 못 쓰는 경우에만. 접근 로그에서는 `***`로 가려짐) |

격리 보장:
- 쿠키는 요청/세션별 ContextVar와 SSE 세션에만 보관되며, 다른 사용자 요청에 사용되지 않습니다.
- 응답 캐시(15초)는 쿠키 전체의 해시로 구분됩니다.
- 사용자(쿠키)별 동시 요청은 4개(`NAVERWORKS_PER_USER_CONCURRENCY`), 서버 전체는 25개(`NAVERWORKS_UPSTREAM_CONCURRENCY`)로 제한됩니다.
- 태스크 생성자는 항상 요청 쿠키의 사용자입니다. 네이버웍스가 `actionUserId`를 무시하므로 서버는 이 값을 보내지 않습니다.

---

## 4. MCP 클라이언트 설정

### 4.1 Claude Desktop · Claude Code · Cursor · VS Code · Opencode

단계별 설정은 사용자 가이드 [client-setup.md](client-setup.md)에 있습니다.

| 클라이언트 | 연결 방식 요약 |
|---|---|
| Claude Desktop | 설정 파일에서 원격 서버에 커스텀 헤더를 직접 지정할 수 없으므로 `npx mcp-remote <URL> --transport sse-only --header "X-Naverworks-Cookie:${NW_COOKIE}"` 로 연결 (Node.js 18+) |
| Claude Code | `claude mcp add --transport sse naverworks <URL> --header "X-Naverworks-Cookie: <쿠키>"` |
| Cursor | `mcp.json`에 `"url"` + `"headers"` |
| VS Code (Copilot) | `mcp.json`에 `"type": "sse"` + `"headers"` (`${input:...}`으로 쿠키를 입력창에서 받기 가능) |
| Opencode | 원격 서버는 Streamable HTTP만 지원 → URL을 **`/mcp/rpc`** 로. 권장: 헤더 없이 등록 후 `opencode mcp auth naverworks`로 OAuth 브라우저 로그인. 또는 `"oauth": false` + 헤더 `{file:~/.config/naverworks/cookie.txt}` (파일이 없으면 설정 전체 로드 실패) → [03-opencode.md](client-setup.md) |

### 4.2 그 밖의 클라이언트

SSE 원격 서버와 커스텀 헤더를 지원하는 클라이언트라면 아래 형태로 등록합니다. 설정 파일 위치와 키 이름은 각 도구의 버전에 따라 다를 수 있으니 해당 도구의 문서를 함께 확인하세요.

**Cline / Roo Code (VS Code 확장) · Antigravity / Gemini CLI** — `mcpServers` 형식:

```json
{
  "mcpServers": {
    "naverworks": {
      "type": "sse",
      "url": "https://naverworks-mcp.example.com/sse",
      "headers": {
        "X-Naverworks-Cookie": "<본인 네이버웍스 쿠키 문자열>"
      }
    }
  }
}
```

헤더를 지원하지 않는 클라이언트는 Claude Desktop처럼 `mcp-remote`를 `command`로 실행하는 방식을 사용합니다.

### 4.3 본인 PC에서 stdio로 실행

서버를 따로 띄우지 않고 클라이언트가 `apps/server.py`를 직접 실행하게 할 수 있습니다 (`local` 모드, 쿠키 설정 불필요). [client-setup.md](client-setup.md) 참고.

---

## 5. 코드에서 직접 호출

MCP 클라이언트가 아닌 Python 코드나 에이전트 프레임워크에서는 `/mcp/call`(도구 실행) 또는 REST API를 호출하면 됩니다. **모든 요청에 쿠키 헤더가 필요합니다.**

```python
import os
import httpx

BASE_URL = "https://naverworks-mcp.example.com"
HEADERS = {"X-Naverworks-Cookie": os.environ["NAVERWORKS_COOKIE"]}  # 쿠키는 코드에 직접 쓰지 말고 환경 변수로


def call_tool(name: str, arguments: dict) -> dict:
    """MCP 도구 실행 → {"content": [{"type": "text", "text": "..."}], "isError": bool}"""
    r = httpx.post(f"{BASE_URL}/mcp/call", json={"name": name, "arguments": arguments},
                   headers=HEADERS, timeout=60)
    r.raise_for_status()
    return r.json()


print(call_tool("list_spaces", {}))

# REST API (네이버웍스 원본 응답을 그대로 반환)
print(httpx.get(f"{BASE_URL}/api/v1/tasks", params={"project_id": "p-..."}, headers=HEADERS, timeout=60).json())
```

LLM의 함수 호출(function calling)에 연결할 때는 `GET /mcp/tools`가 돌려주는 `inputSchema`(JSON Schema)를 도구 정의로 그대로 사용할 수 있습니다. OpenAPI 기반 도구 생성기를 쓰는 경우 `GET /openapi.json`을 사용하되, 쿠키 헤더를 붙이도록 설정해야 합니다.

---

## 6. 도구 목록

두 모드 모두 아래 20개가 제공됩니다. `login_naverworks`만 모드에 따라 동작이 다릅니다.

| 도구 | 설명 | 주요 파라미터 |
|---|---|---|
| `get_auth_status` | 현재 요청/세션의 인증 여부와 쿠키 출처(`http_request`, `mcp_session`, `local_cookie_jar` 등) 확인 | 없음 |
| `set_user_cookie` | 현재 SSE 세션에 쿠키 등록 (`cookiePath`는 local 전용) | `cookie`, `cookiePath` |
| `login_naverworks` | **local**: 서버 PC에서 브라우저를 열어 로그인 후 쿠키 저장 / **multi_user**: 로그인 URL과 쿠키 복사 절차를 안내 (SSE 세션이면 이후 `set_user_cookie`로 등록, `/mcp/rpc`는 OAuth 사용). 쿠키가 없을 때의 `UNAUTHORIZED` 응답에 `nextTool: "login_naverworks"`가 포함됩니다 | `timeoutSeconds`, `force` (local 전용) |
| `list_spaces` | 스페이스 목록 (요약) | `domainId` |
| `get_space` | 스페이스 상세 및 소속 프로젝트 ID | `spaceId` |
| `create_space` | 스페이스 생성 | `spaceName`, `spaceColor` |
| `delete_space` | 스페이스 영구 삭제 | `spaceId` |
| `list_projects` | 스페이스 하위 프로젝트 목록 | `spaceId` |
| `get_project` | 프로젝트 상세 | `projectId` |
| `create_project` | 프로젝트 생성 | `spaceId`, `projectName`, `projectColor`, `projectType` |
| `delete_project` | 프로젝트 영구 삭제 | `projectId` |
| `list_tasks` | 프로젝트 소속 태스크 목록. 요약 형태이고 `{total, offset, returned, hasMore, tasks}`로 돌려줍니다. 기본 50개, 최대 200개까지 받고, `status` 필터를 쓸 수 있습니다. 본문 미리보기는 `includePreview`일 때만 넣습니다 | `projectId` (선택: `status`, `limit`, `offset`, `includePreview`) |
| `get_task` | 태스크 상세 (본문, 상태, 하위 태스크 ID `subTaskIds`) | `taskId` |
| `list_task_comments` | 태스크 댓글 목록. 작성자·본문·시간 요약을 `{total, offset, returned, hasMore, comments}` 형태로 돌려줍니다. 기본 30개, 최대 200개. `rl`은 태스크에서 자동 확인 | `taskId` (선택: `limit`, `offset`, `rl`) |
| `create_task_comment` | 태스크에 댓글 작성. 작성자는 요청 쿠키의 사용자입니다. `parentTaskCommentId`를 주면 답글이 됩니다 | `taskId`, `htmlText` (선택: `parentTaskCommentId`, `rl`) |
| `update_task_comment` | 태스크 댓글 내용을 새 내용으로 교체 | `taskId`, `taskCommentId`, `htmlText` (선택: `rl`) |
| `delete_task_comment` | 태스크 댓글 영구 삭제 | `taskId`, `taskCommentId` (선택: `rl`) |
| `create_task` | 태스크 또는 하위 태스크 생성 | `projectId`, `title`, `htmlText`, `parentTaskId` |
| `update_task_content` | 태스크 본문 수정 | `taskId`, `htmlText` |
| `delete_task` | 태스크 영구 삭제 | `taskId` |

`domainId`·`instanceCode`(`rl`)는 보통 생략합니다. 직접 넣은 값이 항상 우선합니다.

- **`domainId`**: 인자로 받은 ID(`spaceId`, `projectId`, `taskId`, `parentTaskId`)의 `s-/p-/t-{domainId}-{uuid}` 형식에서 추출합니다. ID가 없는 `list_spaces`·`create_space`는 먼저 클라이언트 설정 과정에서 받은 조직 ID를 씁니다. OAuth 로그인에서는 붙여넣은 cURL의 `/rd/{domainId}/`를 읽어 토큰(`nwt_…`)에 담고, 헤더 방식에서는 `X-Naverworks-Domain-Id` 헤더로 받습니다. 둘 다 요청마다 전달되므로 서버를 재시작해도 유지됩니다. 그다음으로 같은 사용자(쿠키)의 이전 호출에서 기억한 값을 씁니다. 그 값이 없으면 로그인한 네이버웍스 웹 페이지(`/space`)에서 찾고, 찾으면 사용자별로 기억합니다. OAuth 로그인 때도 이렇게 찾아 두어서, 로그인 직후에는 추가 조회가 없습니다. 이 방법으로도 알 수 없을 때만 `NAVERWORKS_DOMAIN_ID`(선택, 기본값 없음)를 씁니다. 그것도 없으면 `DOMAIN_ID_UNKNOWN` 오류로 ID를 요청합니다. 다른 조직으로 잘못 요청하지는 않습니다.
- **`rl`**: 스페이스·프로젝트 응답의 `rl`을 프로젝트별로 기억합니다. 모르는 프로젝트에 쓰기 요청(`create_task`, `delete_project`)을 보낼 때는 프로젝트 조회를 1회 먼저 실행해 확인합니다. 조회는 `rl`이 달라도 동작하므로 `get_project`는 추가 호출이 없습니다. 확인에 실패하면 `NAVERWORKS_INSTANCE_CODE`를 씁니다.
- 따라서 서버에 조직 값을 설정하지 않아도 여러 조직의 사용자가 같은 서버를 쓸 수 있습니다.

---

## 7. 문제 해결

### `UNAUTHORIZED` / 401
- `multi_user` 모드에서는 **요청에 실린 사용자 쿠키만** 사용합니다. 헤더 이름(`X-Naverworks-Cookie`)과 값을 확인하세요.
- 쿠키 파일 경로 헤더(`X-Naverworks-Cookie-Path`)는 multi_user에서 무시됩니다. 쿠키 **값**을 보내세요.
- `/mcp/rpc`·`/mcp/call`은 요청마다 헤더(또는 OAuth Bearer 토큰)가 필요합니다. 이전 요청의 `set_user_cookie`는 유지되지 않습니다.
- `/mcp/rpc`가 HTTP 401을 돌려주는 것은 OAuth 로그인 유도입니다. 클라이언트에서 인증을 진행하세요 (Opencode: `opencode mcp auth naverworks`).
- 네이버웍스가 401을 돌려주면 쿠키가 만료된 것입니다. 사용자가 다시 로그인해 새 쿠키를 받아야 합니다. (`/mcp/rpc`의 `tools/call`에서는 이때 HTTP 401로 응답해 클라이언트가 재로그인하도록 합니다.)

### OAuth 로그인이 완료되지 않음
- 로그인 페이지가 `잘못된 인증 요청`을 보이면 `redirect_uri`가 허용 범위(https, localhost)가 아니거나 PKCE(S256)가 빠진 요청입니다.
- `/oauth/token`이 `invalid_grant`이면 인가 코드가 만료(5분)·재사용되었거나, 다른 서버 프로세스가 코드를 발급했습니다 (다중 워커).
- 메타데이터의 주소가 `http://…` 등 실제 외부 주소와 다르면 `PUBLIC_BASE_URL`을 지정하세요.

### 클라이언트가 연결되지 않음
```bash
curl https://<서버>/health                 # {"status":"ok"}
curl -N -H "X-Naverworks-Cookie: <쿠키>" https://<서버>/sse
# event: endpoint
# data: /messages?session_id=...&sessionId=...
```
- `/messages`는 본문 없이 `202 Accepted`만 반환합니다. 응답은 위 SSE 스트림으로 옵니다.
- `/messages`가 `404`이면 SSE 세션이 끊긴 것입니다 (서버 재시작 등). 클라이언트가 `/sse`부터 다시 연결해야 합니다.
- `/messages`가 `503`이면 클라이언트가 SSE 스트림을 읽지 않아 응답 대기열이 가득 찬 상태입니다.

### `403 Forbidden` (local 모드)
local 모드는 `localhost`/`127.0.0.1`/`::1` 이외의 Host·Origin 요청을 거부합니다 (악성 웹페이지·DNS rebinding 차단). 다른 호스트 이름이 필요하면 `LOCAL_ALLOWED_HOSTS`에 추가하세요.

### 브라우저 프론트엔드에서 직접 호출하려면
기본적으로 교차 출처(CORS) 요청을 허용하지 않습니다. `CORS_ALLOW_ORIGINS=https://your-frontend.example.com`처럼 허용할 Origin을 지정하세요.
