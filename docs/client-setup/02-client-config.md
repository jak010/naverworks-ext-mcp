# 2단계. AI 도구에 MCP 서버 등록하기

아래 값 두 개를 준비한 뒤, 사용하는 AI 도구의 항목을 따라 하세요.

| 항목 | 값 |
|---|---|
| **서버 주소** | 운영자에게 받은 주소. 예: `https://naverworks-mcp.example.com/sse` (반드시 `/sse`로 끝남) |
| **쿠키** | [1단계](01-get-cookie.md)에서 복사한 쿠키 문자열 |

모든 도구에 공통으로, 쿠키는 HTTP 헤더 **`X-Naverworks-Cookie`** 로 전달합니다.

> 이 문서의 `https://naverworks-mcp.example.com/sse` 와 `<복사한 쿠키>` 는 예시입니다. 실제 값으로 바꿔 넣으세요.

- [Claude Desktop](#claude-desktop)
- [Claude Code (CLI)](#claude-code-cli)
- [Cursor](#cursor)
- [VS Code (GitHub Copilot)](#vs-code-github-copilot)
- [Opencode](#opencode)
- [그 밖의 도구](#그-밖의-도구)
- [설정 파일에 헤더를 넣을 수 없는 경우](#설정-파일에-헤더를-넣을-수-없는-경우)

---

## Claude Desktop

Claude Desktop 설정 파일은 원격 서버에 커스텀 헤더를 직접 넣는 기능이 없으므로, **`mcp-remote`** 라는 중계 프로그램을 통해 연결합니다.

**사전 준비**: [Node.js](https://nodejs.org) 18 이상 설치 (터미널에서 `node --version`으로 확인)

1. Claude Desktop에서 **설정(Settings) → 개발자(Developer) → 설정 편집(Edit Config)** 을 누르거나, 아래 파일을 직접 엽니다.
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
2. 아래 내용을 추가합니다. (파일에 다른 서버가 이미 있다면 `mcpServers` 안에 `"naverworks"` 항목만 추가)

```json
{
  "mcpServers": {
    "naverworks": {
      "command": "npx",
      "args": [
        "-y",
        "mcp-remote",
        "https://naverworks-mcp.example.com/sse",
        "--transport",
        "sse-only",
        "--header",
        "X-Naverworks-Cookie:${NW_COOKIE}"
      ],
      "env": {
        "NW_COOKIE": "<복사한 쿠키>"
      }
    }
  }
}
```

- 쿠키는 `args`에 직접 넣지 말고 위처럼 **`env`의 `NW_COOKIE`에 넣으세요.** 쿠키에는 공백과 `;`이 들어 있어, `args`에 직접 넣으면 (특히 Windows에서) 값이 잘려 전달될 수 있습니다.
- `"X-Naverworks-Cookie:${NW_COOKIE}"` 는 그대로 두세요. 콜론(`:`) 뒤에 공백을 넣지 않습니다.
- 쿠키 문자열 안에 `"`가 있다면 JSON 규칙에 따라 `\"`로 바꿔야 합니다. (일반적으로는 없음)

3. Claude Desktop을 **완전히 종료**(macOS: `⌘Q`, Windows: 트레이 아이콘에서 종료)한 뒤 다시 실행합니다.
4. 대화 입력창의 도구(🔨/설정) 메뉴에 `naverworks` 도구들이 보이면 연결된 것입니다.

> 연결이 안 되면 **설정 → 개발자** 화면에서 `naverworks` 서버의 로그를 확인하세요.

---

## Claude Code (CLI)

터미널에서 한 번만 등록하면 됩니다. `--scope user`로 등록하면 모든 프로젝트에서 사용할 수 있습니다.

**macOS** — 1단계에서 쿠키를 클립보드에 복사해 둔 상태에서:

```bash
NW_COOKIE="$(pbpaste)"
claude mcp add --transport sse --scope user naverworks \
  https://naverworks-mcp.example.com/sse \
  --header "X-Naverworks-Cookie: $NW_COOKIE"
unset NW_COOKIE
```

**Windows (PowerShell)**:

```powershell
$NW_COOKIE = Get-Clipboard
claude mcp add --transport sse --scope user naverworks https://naverworks-mcp.example.com/sse --header "X-Naverworks-Cookie: $NW_COOKIE"
Remove-Variable NW_COOKIE
```

확인:

```bash
claude mcp list          # naverworks 가 ✓ Connected 로 표시되면 성공
```

- Claude Code 대화 중에는 `/mcp` 명령으로 연결 상태를 볼 수 있습니다.
- 쿠키를 교체할 때는 `claude mcp remove naverworks --scope user` 후 위 명령으로 다시 등록합니다.
- 등록한 쿠키는 사용자 설정 파일(`~/.claude.json`)에 저장됩니다. 프로젝트 공유용 `.mcp.json`(`--scope project`)에는 쿠키를 넣지 마세요.

---

## Cursor

**설정(Settings) → MCP → Add new MCP server** 를 누르거나, 아래 파일을 직접 편집합니다.

- 모든 프로젝트에서 사용: `~/.cursor/mcp.json` (권장 — 쿠키가 프로젝트 폴더에 남지 않음)
- 특정 프로젝트에서만 사용: `<프로젝트>/.cursor/mcp.json` (이 경우 반드시 `.gitignore`에 추가)

```json
{
  "mcpServers": {
    "naverworks": {
      "url": "https://naverworks-mcp.example.com/sse",
      "headers": {
        "X-Naverworks-Cookie": "<복사한 쿠키>"
      }
    }
  }
}
```

저장 후 **Settings → MCP** 화면에서 `naverworks` 옆 표시등이 초록색이 되고 도구 목록이 보이면 성공입니다. (안 보이면 새로고침 아이콘을 누르거나 Cursor 재시작)

---

## VS Code (GitHub Copilot)

VS Code는 쿠키를 설정 파일에 저장하지 않고 **처음 연결할 때 입력창으로 물어보게** 할 수 있어 가장 안전합니다.

명령 팔레트(`Ctrl`/`⌘` + `Shift` + `P`) → **MCP: Open User Configuration** 을 실행해 열린 `mcp.json`에 추가합니다.

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "naverworks-cookie",
      "description": "네이버웍스 쿠키 (X-Naverworks-Cookie)",
      "password": true
    }
  ],
  "servers": {
    "naverworks": {
      "type": "sse",
      "url": "https://naverworks-mcp.example.com/sse",
      "headers": {
        "X-Naverworks-Cookie": "${input:naverworks-cookie}"
      }
    }
  }
}
```

- 서버를 처음 시작할 때 쿠키 입력창이 뜨면 복사한 쿠키를 붙여넣습니다. 입력값은 VS Code가 안전하게 보관합니다.
- Copilot Chat을 **Agent** 모드로 바꾸면 도구 목록에 `naverworks` 도구가 보입니다.
- 쿠키를 교체하려면 명령 팔레트 → **MCP: List Servers** → `naverworks` → 서버를 다시 시작하면서 새 값을 입력합니다.

---

## Opencode

Opencode는 설정 방식이 달라 **[04-opencode.md](04-opencode.md)** 에 따로 정리했습니다. 요약하면:

- 서버 주소 끝을 `/sse`가 아니라 **`/mcp/rpc`** 로 등록합니다. (예: `https://naverworks-mcp.example.com/mcp/rpc`)
- **권장: 브라우저 로그인(OAuth).** 설정에는 주소만 넣고, `opencode mcp auth naverworks`를 실행하면 브라우저에 로그인 페이지가 열립니다. 쿠키는 그 페이지에서 붙여넣습니다.
- 이 방식에서는 `"oauth": false`와 `headers`를 넣지 않습니다.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "naverworks": {
      "type": "remote",
      "url": "https://naverworks-mcp.example.com/mcp/rpc"
    }
  }
}
```

쿠키 파일(`{file:…}`)로 전달하는 방식은 [04-opencode.md](04-opencode.md#다른-도구와-다른-점-3가지)를 보세요. 이 방식은 **파일이 없으면 Opencode 설정 전체가 로드되지 않으니** 주의하세요.

---

## 그 밖의 도구

Cline, Roo Code, Antigravity 등 원격(SSE) MCP 서버와 커스텀 헤더를 지원하는 도구라면 아래 두 가지만 설정하면 됩니다.

- **전송 방식**: SSE (`type: "sse"` 또는 `"remote"`)
- **URL**: `https://naverworks-mcp.example.com/sse`
- **헤더**: `X-Naverworks-Cookie: <복사한 쿠키>` (또는 `Authorization: Bearer <복사한 쿠키>`)

도구별 예시는 [llm-integration-guide.md](../llm-integration-guide.md)에 있습니다. 헤더를 지원하지 않는 도구는 Claude Desktop처럼 `mcp-remote`를 `command`로 실행하는 방식을 사용할 수 있습니다.

---

## 설정 파일에 헤더를 넣을 수 없는 경우

먼저 **브라우저 로그인(OAuth)** 을 시도해 보세요. 도구가 원격 MCP 서버의 OAuth 로그인을 지원하면, 주소를 **`/mcp/rpc`** 로 등록하고 헤더 없이 연결합니다. 쿠키가 없으면 서버가 401로 로그인을 요청하고, 도구가 브라우저에 로그인 페이지를 엽니다. (Opencode에서 확인했습니다. 다른 도구는 버전에 따라 지원 여부가 다릅니다.)

OAuth도 지원하지 않는다면, SSE(`/sse`)로 연결한 뒤 대화창에서 AI에게 쿠키를 전달해 등록할 수 있습니다.

> "네이버웍스 쿠키를 등록해줘: `WORKS_SES=...; ...`" → `set_user_cookie` 도구 호출

다만 다음 이유로 **권장하지 않습니다.**

- 쿠키가 **대화 기록에 남고**, AI 서비스 제공자에게도 전송됩니다.
- 등록은 **현재 연결(SSE 세션)에만** 유지되어, AI 도구를 재시작하거나 연결이 끊기면 다시 등록해야 합니다.
- `/mcp/rpc`로 연결한 경우에는 요청마다 상태가 초기화되므로 **다음 요청부터 바로 사라집니다.** `/mcp/rpc`에서는 OAuth나 헤더를 사용하세요.

AI에게 **"네이버웍스 로그인해줘"** 라고 하면 `login_naverworks` 도구가 로그인 URL과 쿠키 복사 절차를 안내합니다.

---

다음: [README의 연결 확인](README.md#연결-확인) · [문제 해결](README.md#문제-해결)
