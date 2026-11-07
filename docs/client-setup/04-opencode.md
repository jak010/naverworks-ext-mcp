# Opencode 설정 가이드

[Opencode](https://opencode.ai)에 네이버웍스 MCP 서버를 연결하는 방법입니다.
Opencode는 다른 AI 도구와 설정 방식이 달라 별도 문서로 정리했습니다.

> ✅ Opencode **v2.0.26**에서 확인 (2026-11-07)
> - 쿠키 파일 방식: 연결(`✓ connected`), 도구 목록 조회, 쿠키 전달
> - 브라우저 로그인 방식: 쿠키 없이 접속 시 `⚠ needs authentication` 인식까지 확인 (브라우저 로그인 완료 후 연결은 각자 환경에서 확인해 주세요)

## 가장 쉬운 방법: 브라우저 로그인 (OAuth, 권장)

쿠키 파일을 미리 만들 필요가 없습니다. 서버 주소만 등록하면, 쿠키가 없을 때 Opencode가 브라우저로 로그인 페이지를 엽니다.

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

1. `opencode mcp list` → `⚠ naverworks  needs authentication` 이 보이면 정상입니다.
2. `opencode mcp auth naverworks` → 브라우저에 **네이버웍스 MCP 로그인** 페이지가 열립니다.
3. 페이지의 **네이버웍스 열기** 버튼으로 로그인한 뒤, 안내대로 쿠키를 복사해 붙여넣고 **로그인 완료**를 누릅니다.
4. 서버가 네이버웍스에 쿠키를 확인한 뒤 Opencode에 전달합니다. `opencode mcp list` → `✓ naverworks  connected`
5. 쿠키가 만료되면 서버가 다시 401을 돌려주므로 `opencode mcp auth naverworks`를 다시 실행합니다.

> - 이 방식에서는 `"oauth": false`와 `headers`를 **넣지 마세요.** `"oauth": false`는 브라우저 로그인을 막고, `X-Naverworks-Cookie` 헤더가 있으면 그 쿠키가 우선 사용됩니다.
> - 특히 `{file:…}` 헤더는 파일이 없으면 Opencode 설정 전체가 로드되지 않습니다 (아래 문제 해결 참고).
> - 서버 운영자: 리버스 프록시 뒤라면 `PUBLIC_BASE_URL`(예: `https://naverworks-mcp.example.com`)을 지정하세요. 브라우저 로그인을 끄려면 `NAVERWORKS_OAUTH_ENABLED=false`.

아래는 쿠키 파일을 직접 관리하는 방식입니다.

---

## 다른 도구와 다른 점 3가지

| | 다른 도구 (Claude Desktop, Cursor 등) | **Opencode** |
|---|---|---|
| 서버 주소 | `https://…/sse` | **`https://…/mcp/rpc`** — Opencode는 원격 서버를 Streamable HTTP로만 연결하므로 `/sse`는 동작하지 않습니다 |
| 쿠키 전달 | 설정에 쿠키 문자열을 붙여넣기 | **쿠키 파일 경로 지정 가능** — `{file:경로}` 문법으로 내 PC의 쿠키 파일 내용을 읽음 (Python 등 추가 설치 불필요) |
| 쿠키 교체 후 | AI 도구 재시작 | 브라우저 로그인 방식: **`opencode mcp auth naverworks`** 다시 실행 / 쿠키 파일 방식: 파일만 바꾸고 **`opencode service restart`** |

운영자에게 받은 주소가 `https://naverworks-mcp.example.com/sse` 라면 Opencode에는 **`https://naverworks-mcp.example.com/mcp/rpc`** 를 등록합니다.

---

## 1. 쿠키를 파일로 저장 (쿠키 파일 방식)

[01-get-cookie.md의 방법 A](01-get-cookie.md#방법-a-브라우저-개발자-도구-windows--macos--linux-공통-권장)로 쿠키 문자열을 복사한 뒤, 파일로 저장합니다.

**macOS**
```bash
mkdir -p ~/.config/naverworks
pbpaste > ~/.config/naverworks/cookie.txt
chmod 600 ~/.config/naverworks/cookie.txt      # 나만 읽을 수 있도록
```

**Linux** — `pbpaste` 대신 `xclip -o -selection clipboard` (또는 `wl-paste`)

**Windows (PowerShell)**
```powershell
New-Item -ItemType Directory -Force "$HOME\.config\naverworks" | Out-Null
Get-Clipboard | Set-Content -NoNewline "$HOME\.config\naverworks\cookie.txt"
```

파일 규칙:
- 쿠키 문자열 **한 줄만** 저장합니다 (`WORKS_SES=...; WORKS_USER_ID=...; ...`). 맨 앞의 `cookie:` 글자나 따옴표는 넣지 않습니다.
- 끝에 줄바꿈이 있어도 괜찮습니다 (Opencode가 제거하는 것을 확인했습니다).
- `deploy/setup.sh`가 만드는 **Netscape 형식 파일(`proj_cookies.txt`)은 쓸 수 없습니다.** 탭과 여러 줄이 그대로 헤더에 들어가기 때문입니다.
  이 저장소가 있는 Mac이라면 Netscape 파일에서 문자열 파일을 만들 수 있습니다:
  ```bash
  PYTHONPATH=apps .venv/bin/python -c "from app.core.cookie import read_cookie_file; print(read_cookie_file('~/.config/naverworks/proj_cookies.txt'), end='')" > ~/.config/naverworks/cookie.txt
  chmod 600 ~/.config/naverworks/cookie.txt
  ```

---

## 2. Opencode에 서버 등록 (쿠키 파일 방식)

### 방법 A. 설정 파일 편집

전역 설정 파일 **`~/.config/opencode/opencode.json`** 을 엽니다. (Windows: `%USERPROFILE%\.config\opencode\opencode.json`)
파일이 없으면 새로 만들고, 이미 있으면 `mcp` 안에 `naverworks` 항목만 추가합니다.

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "naverworks": {
        "type": "remote",
        "url": "https://naverworks-mcp.example.com/mcp/rpc",
        "oauth": false,
        "headers": {
          "X-Naverworks-Cookie": "{file:~/.config/naverworks/cookie.txt}"
        }
      }
    }
  }
}
```

| 항목 | 의미 |
|---|---|
| `"type": "remote"` | 원격 MCP 서버 |
| `"url"` | 서버 주소 — 끝이 **`/mcp/rpc`** |
| `"oauth": false` | 이 서버는 OAuth가 아니라 헤더로 인증하므로 OAuth 로그인 시도를 끔 |
| `"headers"` | `X-Naverworks-Cookie` 헤더에 쿠키 파일 내용을 넣음. `{file:…}` 경로는 절대 경로, `~/`로 시작하는 경로, 설정 파일 기준 상대 경로를 쓸 수 있음 |

> **기존 설정이 옛 형식인 경우**: `"mcp"` 바로 아래에 서버 이름을 두는 형식(`"mcp": { "github": {...} }`)을 이미 쓰고 있다면, 같은 형식으로 추가해도 됩니다. 두 형식 모두 v2.0.26에서 동작합니다.
>
> ```json
> "mcp": {
>   "naverworks": {
>     "type": "remote",
>     "url": "https://naverworks-mcp.example.com/mcp/rpc",
>     "oauth": false,
>     "enabled": true,
>     "headers": { "X-Naverworks-Cookie": "{file:~/.config/naverworks/cookie.txt}" }
>   }
> }
> ```

### 방법 B. 명령으로 등록

```bash
opencode mcp add naverworks --global \
  --url https://naverworks-mcp.example.com/mcp/rpc \
  --header "X-Naverworks-Cookie={file:~/.config/naverworks/cookie.txt}"
```

- 헤더는 **`이름=값`** 형식입니다. (`이름: 값`으로 쓰면 `Invalid key=value format` 오류)
- `--global`을 빼면 현재 폴더의 프로젝트 설정(`opencode.json`)에 기록됩니다.
- 이 명령은 `"oauth": false`를 넣지 않습니다. 등록 후 설정 파일에 `"oauth": false`를 추가하세요.

### 쿠키를 파일 대신 직접 넣으려면

`"X-Naverworks-Cookie": "<복사한 쿠키 문자열>"` 로 적어도 됩니다. 다만 쿠키가 설정 파일에 남으므로, 그 설정 파일을 공유하거나 커밋하지 않도록 주의하세요. 파일 방식(`{file:…}`)은 설정 파일에 쿠키가 남지 않아 프로젝트 설정(`opencode.json`)에 넣어도 안전합니다.

---

## 3. 연결 확인

```bash
opencode mcp list
```

```
✓ naverworks  connected
```

- 등록 직후 첫 실행에서는 `No MCP servers configured`가 나올 수 있습니다. 백그라운드 서비스가 설정을 읽는 중이니 몇 초 뒤 다시 실행하세요.
- Opencode 대화에서 **"네이버웍스 인증 상태 확인해줘"** → `isAuthenticated: true`, 이어서 **"내 스페이스 목록 보여줘"** 로 최종 확인합니다.

---

## 4. 쿠키 교체 (만료 시)

**브라우저 로그인 방식**: `opencode mcp auth naverworks`를 다시 실행해 로그인 페이지에서 새 쿠키를 붙여넣습니다. 쿠키가 만료되면 도구를 호출할 때 서버가 401을 돌려줍니다. (`opencode mcp list`는 네이버웍스를 호출하지 않으므로 만료 후에도 `connected`로 보일 수 있습니다.)

**쿠키 파일 방식**:

1. 브라우저에서 다시 로그인하고 쿠키를 복사합니다. ([01-get-cookie.md](01-get-cookie.md))
2. **쿠키 파일 내용만** 새 쿠키로 바꿉니다. (위 1단계의 저장 명령을 다시 실행)
3. 백그라운드 서비스를 재시작합니다.
   ```bash
   opencode service restart
   ```

설정 파일(`opencode.json`)은 고칠 필요가 없습니다. Opencode는 백그라운드 서비스가 시작할 때 설정과 `{file:…}` 내용을 읽어 두므로, **Opencode 창만 다시 여는 것으로는 새 쿠키가 반영되지 않습니다.** (재시작 후에는 새 쿠키가 전달되는 것을 확인했습니다)

---

## 5. 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `✗ naverworks failed: Error POSTing to endpoint: {"detail":"Method Not Allowed"} (HTTP 405)` | 주소를 `/sse`로 등록했습니다. **`/mcp/rpc`** 로 바꾸세요. |
| `No MCP servers configured` | 등록 직후라면 몇 초 뒤 다시 실행하세요. 계속 나오면 설정 파일 위치(`~/.config/opencode/opencode.json`)와 JSON 문법(쉼표, 괄호)을 확인하세요. |
| `needs authentication` | 쿠키 없이 접속해 서버가 브라우저 로그인을 요청한 상태입니다. `opencode mcp auth naverworks`로 로그인하세요. 쿠키 파일 방식을 쓰려면 헤더를 넣고 `"oauth": false`를 추가한 뒤 `opencode service restart`. |
| `Invalid key=value format` (`opencode mcp add` 실행 시) | `--header "X-Naverworks-Cookie={file:…}"`처럼 `=`로 연결하세요. |
| `opencode mcp list`가 `UnexpectedStatus: 500` | `{file:…}`이 가리키는 쿠키 파일이 **없습니다.** Opencode v2.0.26은 파일이 없으면 `ConfigInvalidError`로 설정 전체를 버리므로 **다른 MCP 서버까지 모두** 동작하지 않습니다. 로그(`~/.local/share/opencode/log/opencode.log`)에 `ENOENT ... cookie.txt`가 남습니다. 쿠키 파일을 만들거나(아직 쿠키가 없으면 `touch`로 빈 파일이라도) `opencode service restart`. |
| 연결은 되는데 도구가 `UNAUTHORIZED` | 서버가 `NAVERWORKS_OAUTH_ENABLED=false`로 실행 중이고 쿠키 파일이 비어 있습니다. 쿠키 파일에 쿠키를 저장하고 `opencode service restart`. (대화창에 쿠키를 붙여넣어 `set_user_cookie`로 등록해도 `/mcp/rpc`에서는 다음 요청부터 유지되지 않습니다.) |
| 브라우저 로그인 후에도 예전 쿠키가 쓰임 | 설정에 `X-Naverworks-Cookie` 헤더가 남아 있으면 헤더가 우선합니다. 브라우저 로그인 방식에서는 `headers`를 지우세요. |
| `opencode mcp auth naverworks`가 실패 | 서버 주소가 `/mcp/rpc`인지, 설정에 `"oauth": false`가 없는지 확인하세요. 서버 운영자는 `PUBLIC_BASE_URL`이 실제 외부 주소와 같은지 확인합니다. |
| 처음엔 되다가 네이버웍스 오류(401 등) | 쿠키가 만료되었습니다. [4. 쿠키 교체](#4-쿠키-교체-만료-시)를 진행하세요. |
| 쿠키 파일을 바꿨는데 그대로 | `opencode service restart`를 실행하세요. |
| 헤더 값이 깨짐 / 연결 오류 | 쿠키 파일이 Netscape 형식(탭·여러 줄)입니다. 쿠키 **문자열 한 줄**로 저장하세요. |

공통 문제(쿠키 복사, 보안 수칙 등)는 [README](README.md#문제-해결)를 참고하세요.
