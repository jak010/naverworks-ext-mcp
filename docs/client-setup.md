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
2. 네이버웍스 탭에서 개발자 도구(`F12` / `⌥⌘I`)를 엽니다. **Network** 탭에서 새로고침하고, 필터에 `/rd/`를 입력합니다.
3. 아무 요청이나 **마우스 오른쪽 클릭 → Copy → Copy as cURL**을 고릅니다. Windows는 *Copy as cURL (bash)*를 권장합니다.
4. 로그인 페이지로 돌아와 붙여넣고 **로그인 완료**를 누릅니다.

cURL에는 로그인 쿠키와 **조직 ID**(요청 주소의 `/rd/숫자/`)가 함께 들어 있어서, 한 번에 설정됩니다. 서버는 둘을 확인한 뒤 AI 도구에 전달합니다. 서버에는 저장하지 않으므로 서버가 재시작되어도 다시 입력할 필요가 없습니다.

> 네이버웍스 쿠키는 HttpOnly라서 다른 사이트가 자동으로 읽을 수 없으므로, 이 복사 단계가 필요합니다. 붙여넣는 값은 비밀번호와 같으니 로그인 페이지 외에는 붙여넣지 마세요.

## 3. 사용

평소 말하듯 요청하면 됩니다. 이름만 말해도 AI가 ID를 찾아 처리합니다.

| 요청 예시 | 도구 |
|---|---|
| "네이버웍스 인증 상태 확인해줘" | `get_auth_status` |
| "스페이스 목록 보여줘" / "개발팀 스페이스 프로젝트 알려줘" | `list_spaces`, `list_projects` |
| "릴리스 프로젝트 태스크 보여줘" / "○○ 태스크 자세히" | `list_tasks`, `get_task` |
| "○○ 태스크에 달린 댓글 보여줘" / "○○ 태스크에 '확인했습니다' 댓글 달아줘" / "그 댓글을 …로 고쳐줘" / "방금 단 댓글 지워줘" | `list_task_comments`, `create_task_comment`, `update_task_comment`, `delete_task_comment` |
| "○○ 프로젝트에 '설치 가이드' 태스크 만들어줘" (하위 태스크도 가능) | `create_task` |
| "○○ 태스크 본문을 …로 바꿔줘" | `update_task_content` |
| 스페이스·프로젝트 생성/삭제, 태스크·댓글 삭제 | `create_*`, `delete_*` |

- 태스크는 **본문만** 수정할 수 있습니다. 제목, 상태, 담당자는 바꿀 수 없습니다. 댓글은 내용을 수정할 수 있습니다. 태스크 본문과 댓글 모두 수정하면 기존 내용이 **통째로 바뀝니다**.
- `delete_*`는 **영구 삭제**입니다. 실행 전에 대상을 확인하세요.
- 태스크 목록은 토큰을 아끼기 위해 기본 50개까지, 제목과 상태 위주로 보여 줍니다. "다음 50개", "완료된 태스크만", "본문 미리보기 포함해서"처럼 요청하면 범위를 바꿔 다시 조회합니다.

## 4. 문제 해결

| 증상 | 해결 |
|---|---|
| 로그인 창이 열리지 않음 | 주소가 `/mcp/rpc`로 끝나는지 확인하고, 설정에 `headers`나 `"oauth": false`가 있으면 지우세요. 그다음 AI 도구를 재시작하세요 |
| 사용 중에 다시 로그인을 요구함 | 네이버웍스 세션이 만료되었습니다. 열리는 로그인 페이지에서 다시 로그인하세요 (Opencode는 `opencode mcp auth naverworks`) |
| "네이버웍스가 이 쿠키를 거부했습니다" | 만료되었거나 일부만 복사된 값입니다. 네이버웍스에 다시 로그인한 뒤 다시 **Copy as cURL** 하세요 |
| "조직 ID를 찾지 못했습니다" | 주소에 `/rd/숫자/`가 있는 요청을 복사했는지 확인하세요 (Network 탭 필터에 `/rd/` 입력 후 **Copy as cURL**) |
| 스페이스 목록이 `[]` | 다른 조직 계정일 수 있습니다. 운영자에게 문의하세요 |

**브라우저 로그인을 지원하지 않는 도구**라면 주소를 `…/sse`로 등록하고 헤더 `X-Naverworks-Cookie: <cookie 값>`과 `X-Naverworks-Domain-Id: <요청 주소의 /rd/ 뒤 숫자>`를 추가하세요. ([developer-guide.md](developer-guide.md))

## 부록. 로컬 모드 (macOS, 혼자 사용)

서버 없이 내 Mac에서 실행하며, Chrome에 로그인된 세션을 자동으로 사용합니다. 이 경우 로그인 단계가 없습니다.

```bash
make setup     # 가상환경 + Chrome 쿠키 추출 + 연결 테스트
claude mcp add --scope user naverworks -- "$PWD/.venv/bin/python" "$PWD/apps/server.py"
```

세션이 만료되면 AI에게 "네이버웍스 로그인해줘"라고 요청하거나, `.venv/bin/python apps/cli.py refresh-cookie`를 실행하세요.
