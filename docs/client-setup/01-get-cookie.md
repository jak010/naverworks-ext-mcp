# 1단계. 내 네이버웍스 쿠키 복사하기

MCP 서버에 전달할 **쿠키 문자열**을 브라우저에서 복사합니다. 결과물은 아래처럼 `이름=값`이 `; `로 이어진 한 줄짜리 문자열입니다.

```
NNB=XXXX; WORKS_LANGUAGE=ko_KR; WORKS_SES=XXXXXXXX...; WORKS_USER_ID=XXXX...; ... (매우 김)
```

> 💡 브라우저 로그인(OAuth)을 지원하는 도구(Opencode 등)는 이 단계를 미리 할 필요가 없습니다. 로그인 페이지가 열리면 그때 아래 방법 A대로 복사해 붙여넣으면 됩니다.

> ⚠️ 이 문자열은 **비밀번호와 같습니다.** 복사한 뒤에는 AI 도구 설정에만 붙여넣고, 다른 곳에 저장하거나 공유하지 마세요.

---

## 방법 A. 브라우저 개발자 도구 (Windows / macOS / Linux 공통, 권장)

Chrome 또는 Edge 기준입니다. (Firefox·Safari도 메뉴 이름만 조금 다르고 방법은 같습니다.)

1. 브라우저에서 **https://project.worksmobile.com** 에 접속해 로그인합니다.
2. 개발자 도구를 엽니다.
   - Windows / Linux: `F12` 또는 `Ctrl` + `Shift` + `I`
   - macOS: `⌥ Option` + `⌘ Command` + `I`
3. 상단의 **Network(네트워크)** 탭을 선택하고, 페이지를 **새로고침**(`F5` / `⌘R`)합니다.
4. 필터 입력란에 **`api/v1`** 을 입력한 뒤, 목록에서 아무 요청이나 클릭합니다. (예: 이름에 `spaces`, `projects`, `tasks`가 들어간 요청)
5. 오른쪽 **Headers(헤더)** 탭 → **Request Headers(요청 헤더)** 영역에서 **`cookie:`** 항목을 찾습니다.
6. `cookie:` 오른쪽의 **값 전체**를 드래그해 복사합니다. (우클릭 → *Copy value* 메뉴가 있으면 그것을 사용)
   - `cookie:` 라는 글자 자체는 빼고 **값만** 복사합니다.
   - 값이 매우 길어 여러 줄로 보여도 실제로는 한 줄입니다. 중간을 빠뜨리지 않도록 전체를 선택하세요.

> **왜 Application(애플리케이션) 탭의 쿠키 목록이 아니라 Network 탭인가요?**
> Application 탭은 쿠키가 하나씩 따로 보여 직접 이어 붙여야 하지만, Network 탭의 요청 헤더에는 실제로 서버에 보내지는 쿠키 전체가 이미 한 줄로 합쳐져 있습니다.

### 복사한 값 점검

- `WORKS_SES=` 가 포함되어 있어야 합니다.
- 맨 앞이 `cookie:` 로 시작하거나, 앞뒤에 따옴표(`"`)가 붙어 있으면 지워주세요.

---

## 방법 B. macOS + 이 저장소가 있는 경우 (Chrome 자동 추출)

저장소를 내려받아 설치한 Mac이라면 Chrome에 로그인된 세션에서 쿠키를 자동으로 꺼낼 수 있습니다.

```bash
cd tpjt-naverworks-mcp
deploy/setup.sh       # 최초 1회: 가상환경 설치 + Chrome 쿠키 추출 (~/.config/naverworks/proj_cookies.txt)
# 이미 설치했다면 쿠키만 갱신:
.venv/bin/python apps/cli.py refresh-cookie

# 쿠키 문자열을 화면에 출력하지 않고 클립보드로 복사
PYTHONPATH=apps .venv/bin/python -c "from app.core.cookie import read_cookie_file; print(read_cookie_file('~/.config/naverworks/proj_cookies.txt'), end='')" | pbcopy
```

- 처음 실행할 때 macOS가 **"Chrome Safe Storage" 키체인 접근 허용**을 물을 수 있습니다. 허용해야 쿠키를 읽을 수 있습니다.
- 이제 클립보드에 쿠키 문자열이 들어 있으니 [2단계](02-client-config.md)에서 붙여넣으면 됩니다.

---

## 쿠키를 파일로 저장하기 (Opencode)

> Opencode 전체 설정 방법은 [04-opencode.md](04-opencode.md)를 보세요. Opencode는 **브라우저 로그인(OAuth)** 을 쓰면 쿠키 파일이 필요 없습니다. 아래는 쿠키 파일 방식을 쓸 때만 해당합니다.

Opencode처럼 설정에서 **파일 경로로 쿠키를 읽을 수 있는 도구**를 쓴다면, 복사한 쿠키 문자열을 파일로 저장해 둡니다. 쿠키가 설정 파일에 남지 않고, 교체할 때도 이 파일만 바꾸면 됩니다.

방법 A로 쿠키를 복사한 상태(클립보드)에서:

**macOS / Linux**
```bash
mkdir -p ~/.config/naverworks
pbpaste > ~/.config/naverworks/cookie.txt        # Linux: xclip -o -selection clipboard > ...
chmod 600 ~/.config/naverworks/cookie.txt        # 나만 읽을 수 있도록
```

**Windows (PowerShell)**
```powershell
New-Item -ItemType Directory -Force "$HOME\.config\naverworks" | Out-Null
Get-Clipboard | Set-Content -NoNewline "$HOME\.config\naverworks\cookie.txt"
```

- 파일에는 쿠키 문자열 **한 줄만** 들어 있어야 합니다. (`cookie:` 글자나 따옴표 없이)
- Opencode 설정에 `{file:…}`로 이 파일을 지정했다면 **파일을 지우지 마세요.** 파일이 없으면 Opencode 설정 전체가 로드되지 않습니다.
- 방법 B의 Netscape 형식 파일(`proj_cookies.txt`)과는 다른 파일입니다. 방법 B를 쓴 경우 마지막 명령의 `| pbcopy`를 `> ~/.config/naverworks/cookie.txt`로 바꾸면 문자열 파일을 바로 만들 수 있습니다.

---

## 쿠키는 언제 다시 복사해야 하나요?

- 네이버웍스 세션이 **만료**되면(일정 시간 경과, 비밀번호 변경 등) AI 도구에서 오류가 나기 시작합니다.
- 브라우저에서 네이버웍스를 **로그아웃**하면 그 쿠키도 더 이상 동작하지 않을 수 있습니다.

이럴 때는 다시 로그인한 뒤 위 방법으로 쿠키를 새로 복사해 [AI 도구 설정](02-client-config.md)의 값을 교체하고, AI 도구를 재시작하세요.

다음 단계: **[2단계. AI 도구에 등록하기 →](02-client-config.md)**
