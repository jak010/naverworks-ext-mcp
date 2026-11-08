# 클라이언트 설정 가이드

AI 도구에는 **서버 주소만 등록**하면 됩니다. 처음 연결할 때 브라우저에 **네이버웍스 MCP 로그인** 페이지가 열리고, 페이지 안내대로 로그인하면 연결이 끝납니다. 설정 파일에 쿠키를 넣지 않습니다.

- 서버 주소: `https://naverworks-mcp.example.com/mcp/rpc` (예시입니다. 운영자에게 받은 주소로 바꾸세요. 직접 띄운 서버라면 `http://localhost:9050/mcp/rpc`)
- 주소 끝은 반드시 **`/mcp/rpc`** 여야 합니다. `/sse`로 등록하면 로그인 창이 열리지 않습니다.

## 1. AI 도구에 등록

**Claude Code**

```bash
claude mcp add --transport http --scope user naverworks https://naverworks-mcp.example.com/mcp/rpc
```

등록한 뒤 Claude Code에서 `/mcp`를 실행하고, `naverworks`를 고른 다음 **Authenticate**를 누릅니다.

**Cursor** (`~/.cursor/mcp.json`)

```json
{ "mcpServers": { "naverworks": { "url": "https://naverworks-mcp.example.com/mcp/rpc" } } }
```

**Settings → MCP**에서 `naverworks` 옆의 **Login**(Needs login)을 누릅니다.

**VS Code (Copilot)** (`mcp.json`)

```json
{ "servers": { "naverworks": { "type": "http", "url": "https://naverworks-mcp.example.com/mcp/rpc" } } }
```

서버를 시작하면 인증을 허용할지 묻습니다. **Allow**를 누릅니다.

**Opencode** (`opencode.json`)

```json
{ "mcp": { "naverworks": { "type": "remote", "url": "https://naverworks-mcp.example.com/mcp/rpc" } } }
```

설정한 뒤 터미널에서 `opencode mcp auth naverworks`를 실행합니다.

**Claude Desktop** (`claude_desktop_config.json`, Node.js 18 이상 필요)

```json
{ "mcpServers": { "naverworks": {
  "command": "npx", "args": ["-y", "mcp-remote", "https://naverworks-mcp.example.com/mcp/rpc"] } } }
```

Claude Desktop을 다시 시작하면 브라우저가 자동으로 열립니다.

## 2. 브라우저에서 로그인

열린 **네이버웍스 MCP 로그인** 페이지에서 다음 순서로 진행합니다.

1. **네이버웍스 열기 / 로그인**을 눌러 네이버웍스에 로그인합니다.
2. 네이버웍스 탭에서 개발자 도구(`F12` / `⌥⌘I`)를 엽니다. **Network** 탭에서 새로고침한 뒤 `api/v1` 요청을 클릭합니다.
3. Request Headers의 `cookie:` 값 전체를 복사합니다.
4. 로그인 페이지로 돌아와 복사한 값을 붙여넣고 **로그인 완료**를 누릅니다.

서버가 네이버웍스에 확인한 뒤 로그인을 마치면 AI 도구로 돌아갑니다. 이 값은 AI 도구가 안전하게 보관하므로 다시 입력할 필요가 없습니다.

> 네이버웍스 쿠키는 HttpOnly라서 다른 사이트가 자동으로 읽을 수 없습니다. 그래서 3~4단계는 직접 복사해 붙여넣어야 합니다. 이 값은 비밀번호와 같으니 로그인 페이지 외에는 붙여넣지 마세요.

## 3. 사용

평소 말하듯 요청하면 됩니다. 이름만 말해도 AI가 ID를 찾아 처리합니다.

| 요청 예시 | 도구 |
|---|---|
| "네이버웍스 인증 상태 확인해줘" | `get_auth_status` |
| "스페이스 목록 보여줘" / "개발팀 스페이스 프로젝트 알려줘" | `list_spaces`, `list_projects` |
| "릴리스 프로젝트 태스크 보여줘" / "○○ 태스크 자세히" | `list_tasks`, `get_task` |
| "○○ 프로젝트에 '설치 가이드' 태스크 만들어줘" (하위 태스크도 가능) | `create_task` |
| "○○ 태스크 본문을 …로 바꿔줘" | `update_task_content` |
| 스페이스·프로젝트 생성/삭제, 태스크 삭제 | `create_*`, `delete_*` |

- 수정할 수 있는 것은 태스크 **본문뿐**입니다. 제목, 상태, 담당자는 바꿀 수 없습니다. 본문 수정은 기존 내용을 통째로 바꿉니다.
- `delete_*`는 **영구 삭제**입니다. 실행 전에 대상을 확인하세요.
- 태스크 목록은 토큰을 아끼기 위해 기본 50개까지, 제목과 상태 위주로 보여 줍니다. "다음 50개", "완료된 태스크만", "본문 미리보기 포함해서"처럼 요청하면 범위를 바꿔 다시 조회합니다.

## 4. 문제 해결

| 증상 | 해결 |
|---|---|
| 로그인 창이 열리지 않음 | 주소가 `/mcp/rpc`로 끝나는지 확인하고, 설정에 `headers`나 `"oauth": false`가 있으면 지우세요. 그다음 AI 도구를 재시작하세요 |
| 사용 중에 다시 로그인을 요구함 | 네이버웍스 세션이 만료되었습니다. 열리는 로그인 페이지에서 다시 로그인하세요 (Opencode는 `opencode mcp auth naverworks`) |
| "네이버웍스가 이 쿠키를 거부했습니다" | 만료되었거나 일부만 복사된 값입니다. 네이버웍스에 다시 로그인한 뒤 `cookie:` 값 **전체**를 복사하세요 |
| 스페이스 목록이 `[]` | 다른 조직 계정일 수 있습니다. 운영자에게 문의하세요 |

**브라우저 로그인을 지원하지 않는 도구**라면 주소를 `…/sse`로 등록하고 헤더 `X-Naverworks-Cookie: <위 3단계에서 복사한 값>`을 추가하세요. ([developer-guide.md](developer-guide.md))

## 부록. 로컬 모드 (macOS, 혼자 사용)

서버 없이 내 Mac에서 실행하며, Chrome에 로그인된 세션을 자동으로 사용합니다. 이 경우 로그인 단계가 없습니다.

```bash
make setup     # 가상환경 + Chrome 쿠키 추출 + 연결 테스트
claude mcp add --scope user naverworks -- "$PWD/.venv/bin/python" "$PWD/apps/server.py"
```

세션이 만료되면 AI에게 "네이버웍스 로그인해줘"라고 요청하거나, `.venv/bin/python apps/cli.py refresh-cookie`를 실행하세요.
