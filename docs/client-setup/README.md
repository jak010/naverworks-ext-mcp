# 클라이언트 PC MCP 설정 가이드

네이버웍스 Project MCP 서버를 **내 PC의 AI 도구**(Claude Desktop, Claude Code, Cursor, VS Code 등)에 연결하는 방법입니다.
연결하면 AI에게 "내 프로젝트의 태스크 목록 보여줘", "OO 프로젝트에 태스크 만들어줘"처럼 요청해 네이버웍스의 스페이스·프로젝트·태스크를 조회/생성/수정/삭제할 수 있습니다.

## 동작 방식

```
 내 PC                                            MCP 서버 (운영자)                  네이버웍스
┌──────────────────────────┐   SSE + 내 쿠키   ┌──────────────────────┐  내 쿠키   ┌────────────────────┐
│ AI 도구 (Claude, Cursor…) │ ───────────────▶ │ naverworks-mcp       │ ─────────▶ │ project.worksmobile │
│  설정: 서버 주소 + 내 쿠키 │ ◀─────────────── │ (사용자별 쿠키 격리) │ ◀───────── │                    │
└──────────────────────────┘                   └──────────────────────┘            └────────────────────┘
```

- MCP 서버는 계정을 따로 만들지 않습니다. **각 사용자가 자신의 네이버웍스 로그인 쿠키를 직접 전달**하고, 서버는 그 쿠키로 사용자 본인 권한으로만 네이버웍스를 호출합니다.
- 쿠키를 전달하지 않으면 모든 도구가 `UNAUTHORIZED`를 반환합니다. 다른 사용자의 쿠키나 서버 운영자의 쿠키가 대신 사용되는 일은 없습니다.
- **브라우저 로그인(OAuth)**: 주소가 `/mcp/rpc`이고 MCP OAuth를 지원하는 도구(Opencode 등)는 쿠키를 설정에 넣지 않아도 됩니다. 쿠키 없이 접속하면 서버가 로그인을 요청하고, 도구가 브라우저에 **네이버웍스 MCP 로그인** 페이지를 엽니다. 그 페이지에서 쿠키를 한 번 붙여넣으면 서버가 확인한 뒤 도구에 전달합니다. ([Opencode 가이드](04-opencode.md#가장-쉬운-방법-브라우저-로그인-oauth-권장))
- 태스크 등은 항상 **쿠키 주인(나)의 이름으로** 생성됩니다.

## 최종 체크리스트 — 사용자가 할 일

공용 서버에 연결할 때 **사용자 PC에 Python이나 이 저장소는 필요 없습니다.** (Claude Desktop만 Node.js 18 이상 필요)

**준비물**
- [ ] 운영자에게 받은 **MCP 서버 주소** — 예: `https://naverworks-mcp.example.com/sse` (`https://`로 시작하고 `/sse`로 끝남)
- [ ] 네이버웍스에 로그인할 수 있는 **브라우저** (Chrome, Edge, Firefox, Safari)
- [ ] 사용할 **AI 도구** 1개 (Claude Desktop / Claude Code / Cursor / VS Code / Opencode)

**설정 (최초 1회, 약 5분)**

| # | 할 일 | 자세히 |
|---|---|---|
| 1 | 브라우저에서 `https://project.worksmobile.com` 로그인 → 개발자 도구(`F12` / `⌥⌘I`) **Network** 탭 → 새로고침 → `api/v1` 요청 클릭 → Request Headers의 **`cookie` 값 전체 복사** | [01-get-cookie.md](01-get-cookie.md) |
| 2 | AI 도구에 **서버 주소 + 쿠키(`X-Naverworks-Cookie` 헤더)** 등록 — 도구별 방법은 아래 표 | [02-client-config.md](02-client-config.md) |
| 3 | AI 도구를 **완전히 종료했다가 다시 실행** | — |
| 4 | AI에게 **"네이버웍스 인증 상태 확인해줘"** → `isAuthenticated: true` 확인, 이어서 **"내 스페이스 목록 보여줘"** | [연결 확인](#연결-확인) |

| AI 도구 | 2단계에서 할 일 |
|---|---|
| Claude Desktop | `claude_desktop_config.json`에 `npx mcp-remote <서버 주소> ...` 항목 추가, 쿠키는 `env`의 `NW_COOKIE`에 붙여넣기 → [설정 예시](02-client-config.md#claude-desktop) |
| Claude Code | 터미널에서 `claude mcp add --transport sse --scope user naverworks <서버 주소> --header "X-Naverworks-Cookie: <쿠키>"` → [설정 예시](02-client-config.md#claude-code-cli) |
| Cursor | `~/.cursor/mcp.json`에 `"url"`과 `"headers": {"X-Naverworks-Cookie": "<쿠키>"}` 추가 → [설정 예시](02-client-config.md#cursor) |
| VS Code (Copilot) | `mcp.json`에 서버 추가 후, 첫 연결 때 뜨는 입력창에 쿠키 붙여넣기 → [설정 예시](02-client-config.md#vs-code-github-copilot) |
| Opencode | `opencode.json`에 주소 **`…/mcp/rpc`** 만 등록 → `opencode mcp auth naverworks`로 **브라우저 로그인** (1단계 쿠키 복사는 로그인 페이지에서 진행). 쿠키 파일 방식도 가능 → [Opencode 가이드](04-opencode.md) |

**유지 관리**
- 쿠키가 **만료**되면(갑자기 오류가 나기 시작하면) 1번을 다시 해서 새 쿠키로 **설정 값만 교체**하고 AI 도구를 재시작합니다. (Opencode는 브라우저 로그인 방식이면 `opencode mcp auth naverworks`를 다시 실행, 쿠키 파일 방식이면 파일만 바꾸고 `opencode service restart`)
- 쿠키는 비밀번호와 같습니다. 공유하거나 깃에 커밋하지 마세요. ([보안 수칙](#보안-수칙-꼭-읽어주세요))

> Opencode 사용자는 [04-opencode.md](04-opencode.md)를 따라 하세요. (주소가 `/mcp/rpc`이고, 브라우저 로그인으로 쿠키를 전달할 수 있습니다)
>
> 서버를 운영자 없이 **내 Mac에서 직접 실행**하려면 [03-local-mode.md](03-local-mode.md)를 보세요. 이 경우에는 Python이 필요하지만, 쿠키를 복사할 필요 없이 Chrome 로그인 정보를 자동으로 사용합니다.

## 연결 확인

AI 도구에서 새 대화를 열고 다음과 같이 요청합니다.

1. **"네이버웍스 인증 상태 확인해줘"** → `get_auth_status` 도구가 호출되고 `isAuthenticated: true`가 나오면 쿠키가 정상 전달된 것입니다.
2. **"내 네이버웍스 스페이스 목록 보여줘"** → `list_spaces` 결과로 내가 속한 스페이스가 보이면 완료입니다.

## 사용할 수 있는 도구

| 분류 | 도구 | 설명 |
|---|---|---|
| 인증 | `get_auth_status` | 현재 연결에 쿠키가 전달되었는지 확인 |
| | `set_user_cookie` | 대화 중에 쿠키 등록 (설정 파일에 헤더를 넣을 수 없을 때만, **SSE 연결에서만 유지**, [주의사항](02-client-config.md#설정-파일에-헤더를-넣을-수-없는-경우)) |
| | `login_naverworks` | 로그인 방법 안내 (공용 서버: 로그인 URL과 쿠키 복사 절차 / 로컬 모드: 브라우저를 열어 자동 로그인) |
| 스페이스 | `list_spaces` / `get_space` / `create_space` / `delete_space` | 스페이스 조회·생성·삭제 |
| 프로젝트 | `list_projects` / `get_project` / `create_project` / `delete_project` | 스페이스 하위 프로젝트 조회·생성·삭제 |
| 태스크 | `list_tasks` / `get_task` / `create_task` / `update_task_content` / `delete_task` | 태스크·하위 태스크 조회·생성·본문 수정·삭제 |

> `delete_*` 도구는 **영구 삭제**입니다. AI가 삭제를 실행하기 전에 대상을 꼭 확인하세요.

## 보안 수칙 (꼭 읽어주세요)

네이버웍스 쿠키는 **비밀번호와 같습니다.** 쿠키를 가진 사람은 로그아웃 전까지 내 네이버웍스 계정으로 무엇이든 할 수 있습니다.

- 쿠키를 다른 사람에게 보내거나, 메신저/이슈/깃 저장소에 붙여넣지 마세요.
- 쿠키가 들어간 설정 파일(`claude_desktop_config.json`, `.cursor/mcp.json` 등)을 **깃에 커밋하지 마세요.** 프로젝트 폴더 안의 설정 파일이라면 `.gitignore`에 추가하세요.
- 서버 주소는 반드시 **`https://`** 로 시작해야 합니다. (`http://`는 내 PC에서 직접 띄운 `localhost` 서버에만 사용)
- 신뢰할 수 있는 운영자가 제공한 서버에만 연결하세요. 서버는 요청을 처리하는 동안 내 쿠키를 다룹니다.
- 쿠키가 유출된 것 같다면 네이버웍스에서 **로그아웃**해 세션을 끊고, 다시 로그인해 새 쿠키로 교체하세요.

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| AI 도구에 네이버웍스 도구가 보이지 않음 | 설정 저장 후 AI 도구를 **완전히 종료했다가 다시 실행**하세요. 서버 주소가 `/sse`로 끝나는지 확인하세요. Claude Desktop은 [Node.js](https://nodejs.org) 18 이상이 설치되어 있어야 합니다. |
| `UNAUTHORIZED` (쿠키가 제공되지 않았습니다) | 헤더 이름이 정확히 `X-Naverworks-Cookie`인지, 쿠키 값이 비어 있지 않은지 확인하세요. 값 앞뒤에 따옴표나 `cookie:` 글자가 섞여 들어가지 않았는지도 확인하세요. |
| 처음엔 되다가 갑자기 오류 (네이버웍스 401 등) | 쿠키가 **만료**되었습니다. 네이버웍스에 다시 로그인해 [쿠키를 새로 복사](01-get-cookie.md)하고 설정을 교체한 뒤 AI 도구를 재시작하세요. 브라우저에서 로그아웃해도 끊길 수 있습니다. |
| 스페이스 목록이 빈 배열 `[]` | 이 서비스가 대상으로 하는 조직과 다른 네이버웍스 조직의 계정일 수 있습니다. 운영자에게 문의하세요. |
| `X-Naverworks-Cookie-Path` 헤더가 동작하지 않음 | 정상입니다. 파일 경로는 **서버 PC의 파일**을 가리키므로 공용 서버에서는 무시됩니다. 쿠키 **값**을 `X-Naverworks-Cookie`로 전달하세요. |
| `login_naverworks`가 브라우저를 열지 않음 | 정상입니다. 공용 서버는 사용자 PC의 브라우저를 열 수 없어서 로그인 URL과 쿠키 복사 절차를 안내합니다. SSE(`/sse`) 연결이라면 복사한 쿠키를 대화창에 붙여넣어 `set_user_cookie`로 등록할 수 있습니다. `/mcp/rpc` 연결(Opencode 등)은 요청마다 상태가 초기화되어 대화 중 등록이 유지되지 않으므로 **브라우저 로그인(OAuth)** 이나 헤더를 사용하세요. |
| `needs authentication` / 브라우저 로그인 페이지가 열림 | `/mcp/rpc`에 쿠키 없이 접속해 서버가 로그인을 요청한 정상 상태입니다. 열린 페이지에서 로그인하세요. (Opencode: `opencode mcp auth naverworks`) |
| 로그인 페이지에서 "네이버웍스가 이 쿠키를 거부했습니다" | 쿠키가 만료되었거나 일부만 복사되었습니다. 네이버웍스에 다시 로그인한 뒤 `cookie:` 값 **전체**를 새로 복사하세요. |
| `403 Forbidden` | 내 PC에서 직접 띄운 로컬 모드 서버에 `localhost` 이외의 주소로 접속한 경우입니다. [03-local-mode.md](03-local-mode.md#문제-해결) 참고. |

그 밖의 클라이언트(Cline, Roo Code, Antigravity 등)와 코드에서 직접 호출하는 방법은 [llm-integration-guide.md](../llm-integration-guide.md)를 참고하세요.
