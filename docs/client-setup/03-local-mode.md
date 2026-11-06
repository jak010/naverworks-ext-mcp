# 부록. 내 PC에서 직접 실행하기 (로컬 모드)

운영자가 띄운 공용 서버 대신, **내 PC에서 MCP 서버를 직접 실행**하는 방법입니다. 나 혼자 사용하는 경우에 적합합니다.

| | 공용 서버 연결 ([README](README.md)) | 로컬 모드 (이 문서) |
|---|---|---|
| 서버 실행 | 운영자 | 내 PC |
| 쿠키 전달 | 설정에 쿠키를 직접 붙여넣기 | **자동** — Chrome에 로그인된 세션에서 추출 (macOS) |
| 쿠키 만료 시 | 브라우저에서 다시 복사 | 명령 한 줄로 갱신, 또는 AI에게 "네이버웍스 로그인해줘" |
| 필요한 것 | AI 도구 (+ Claude Desktop은 Node.js) | Python 3.10 이상, 저장소 소스, (자동 추출은 macOS + Chrome) |

로컬 모드(`NAVERWORKS_AUTH_MODE=local`)에서는 서버가 내 PC에 저장된 쿠키 파일(`~/.config/naverworks/proj_cookies.txt`)을 자동으로 사용합니다. 그래서 **외부에서 접근할 수 없도록** 기본적으로 `127.0.0.1`(내 PC)에만 열리고, `localhost`가 아닌 웹페이지에서 오는 요청은 차단됩니다.

---

## 1. 설치 (macOS)

```bash
git clone <저장소 주소> tpjt-naverworks-mcp
cd tpjt-naverworks-mcp
deploy/setup.sh      # 또는 make setup
```

`deploy/setup.sh`가 하는 일:

1. Python 가상환경(`.venv`)을 만들고 의존성을 설치합니다. ([uv](https://docs.astral.sh/uv/)가 있으면 uv를 사용)
2. Chrome에 로그인된 네이버웍스 세션에서 쿠키를 추출해 `~/.config/naverworks/proj_cookies.txt`에 저장합니다.
   - 로그인이 안 되어 있으면 Chrome으로 로그인 페이지를 열어 줍니다. 로그인 후 터미널에서 Enter를 누르세요.
   - macOS가 **"Chrome Safe Storage" 키체인 접근**을 물으면 허용합니다.
3. 네이버웍스 API 연결을 테스트합니다. (`🎉 네이버웍스 API 연결 성공!`이 나오면 완료)

---

## 2. AI 도구에 등록 (stdio 방식, 권장)

AI 도구가 필요할 때 `apps/server.py`를 직접 실행하는 방식입니다. 따로 서버를 띄워 둘 필요가 없고, 쿠키를 설정에 넣지 않아도 됩니다.

아래 예시의 `/Users/me/tpjt-naverworks-mcp`는 **저장소의 실제 절대 경로**로 바꾸세요. (저장소 폴더에서 `pwd`로 확인)

### Claude Desktop

`~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "naverworks": {
      "command": "/Users/me/tpjt-naverworks-mcp/.venv/bin/python",
      "args": ["/Users/me/tpjt-naverworks-mcp/apps/server.py"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add --scope user naverworks -- /Users/me/tpjt-naverworks-mcp/.venv/bin/python /Users/me/tpjt-naverworks-mcp/apps/server.py
claude mcp list
```

### Cursor

`~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "naverworks": {
      "command": "/Users/me/tpjt-naverworks-mcp/.venv/bin/python",
      "args": ["/Users/me/tpjt-naverworks-mcp/apps/server.py"]
    }
  }
}
```

### VS Code (GitHub Copilot)

명령 팔레트 → **MCP: Open User Configuration**:

```json
{
  "servers": {
    "naverworks": {
      "type": "stdio",
      "command": "/Users/me/tpjt-naverworks-mcp/.venv/bin/python",
      "args": ["/Users/me/tpjt-naverworks-mcp/apps/server.py"]
    }
  }
}
```

등록 후 AI 도구를 재시작하고 [연결 확인](README.md#연결-확인)을 진행하세요. `get_auth_status`의 `cookieSource`가 `local_cookie_jar`로 나오면 정상입니다.

---

## 3. (선택) HTTP 서버로 실행

Swagger 문서(`/docs`)나 웹 대시보드(`/dashboard`)도 함께 쓰고 싶다면 HTTP 서버를 로컬 모드로 띄웁니다.

```bash
NAVERWORKS_AUTH_MODE=local deploy/run.sh
# → http://127.0.0.1:9050/docs , http://127.0.0.1:9050/dashboard
```

AI 도구에는 헤더 없이 주소만 등록합니다. (예: Cursor. Opencode는 `http://localhost:9050/mcp/rpc`)

```json
{
  "mcpServers": {
    "naverworks": { "url": "http://localhost:9050/sse" }
  }
}
```

> 로컬 쿠키 파일도 없는 상태에서 `/mcp/rpc`로 접속하면, 서버가 401로 브라우저 로그인(OAuth)을 요청합니다. 쿠키 파일이 있으면 로그인 없이 바로 연결됩니다.

> ⚠️ 로컬 모드 서버는 내 쿠키를 자동으로 사용하므로 `HOST=0.0.0.0` 등으로 **외부에 열지 마세요.** 같은 네트워크의 누구나 내 계정으로 요청할 수 있게 됩니다. 여러 사람이 쓰는 서버는 기본값인 `multi_user` 모드로 운영해야 합니다.

---

## 4. 쿠키 갱신

쿠키가 만료되어 오류가 나면 다음 중 하나를 실행합니다.

- 터미널: `.venv/bin/python apps/cli.py refresh-cookie`
  (Chrome 세션도 만료되었다면 `.venv/bin/python apps/cli.py login` — 브라우저가 열리고 로그인하면 자동 저장)
- AI에게: **"네이버웍스 로그인해줘"** → `login_naverworks` 도구가 브라우저를 열고 로그인 완료를 감지해 쿠키를 저장합니다. (브라우저를 직접 여는 동작은 로컬 모드 전용입니다. 공용 서버에서는 같은 도구가 로그인 방법만 안내합니다.)

stdio 방식은 다음 요청부터 바로 새 쿠키를 사용합니다. (AI 도구 재시작 불필요)

---

## Windows / Linux에서 사용하기

Chrome 쿠키 자동 추출은 macOS 키체인을 사용하므로 macOS에서만 동작합니다. 다른 OS에서는 쿠키를 직접 지정합니다.

1. 저장소를 내려받고 의존성을 설치합니다.
   ```bash
   python -m venv .venv
   .venv/bin/pip install -r deploy/requirements.txt   # Windows: .venv\Scripts\pip install -r deploy\requirements.txt
   ```
2. [1단계 문서의 방법 A](01-get-cookie.md#방법-a-브라우저-개발자-도구-windows--macos--linux-공통-권장)로 쿠키를 복사합니다.
3. AI 도구 설정의 `env`에 쿠키를 넣습니다. (예: Claude Desktop, Windows)
   ```json
   {
     "mcpServers": {
       "naverworks": {
         "command": "C:\\Users\\me\\tpjt-naverworks-mcp\\.venv\\Scripts\\python.exe",
         "args": ["C:\\Users\\me\\tpjt-naverworks-mcp\\apps\\server.py"],
         "env": { "NAVERWORKS_COOKIE": "<복사한 쿠키>" }
       }
     }
   }
   ```
   쿠키가 만료되면 `NAVERWORKS_COOKIE` 값을 새로 복사한 쿠키로 바꾸고 AI 도구를 재시작합니다.

---

## 문제 해결

| 증상 | 원인 / 해결 |
|---|---|
| `deploy/setup.sh`가 Python 관련 오류로 실패 | 손상된 `.venv`는 스크립트가 자동으로 다시 만듭니다. 그래도 실패하면 `rm -rf .venv` 후 `deploy/setup.sh`를 다시 실행하세요. |
| `⚠️ Chrome에서 네이버웍스 쿠키를 찾지 못했습니다` | Chrome(다른 브라우저 아님)에서 `https://project.worksmobile.com`에 로그인했는지 확인하세요. 키체인 접근 요청을 거부했다면 다시 실행해 허용하세요. |
| `cookieSource`가 `none`, 도구가 `UNAUTHORIZED` | 쿠키 파일이 없거나 만료되었습니다. [쿠키 갱신](#4-쿠키-갱신)을 실행하세요. HTTP 서버라면 `NAVERWORKS_AUTH_MODE=local`로 띄웠는지 확인하세요. |
| `403 Forbidden` (`local mode accepts requests from localhost only`) | 로컬 모드 서버에 `localhost`/`127.0.0.1` 이외의 주소로 접속했거나, 다른 웹사이트에서 호출한 요청입니다. 주소를 `http://localhost:9050`으로 바꾸세요. 다른 호스트 이름이 꼭 필요하면 `LOCAL_ALLOWED_HOSTS`에 추가합니다. |
| AI 도구에서 서버가 시작되지 않음 | 설정의 `command`/`args` 경로가 **절대 경로**인지, 해당 경로에 `.venv/bin/python`과 `apps/server.py`가 있는지 확인하세요. 터미널에서 `<python 경로> <apps/server.py 경로>`를 직접 실행해 오류 메시지를 볼 수 있습니다. (정상이면 `NAVER WORKS MCP Stdio Server 시작됨` 로그 한 줄이 나오고 입력을 기다립니다 — `Ctrl+C`로 종료) |
