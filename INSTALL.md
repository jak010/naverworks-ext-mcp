# 설치 가이드 (요약)

네이버웍스 Project MCP 서버를 내 환경에 연결하는 방법을 한 장으로 정리했습니다. 자세한 내용은 각 단계의 링크를 보세요.

## 0. 어떤 방식으로 쓸지 고르기

| 상황 | 방식 | 이동 |
|---|---|---|
| 운영자가 띄운 **공용 서버**가 있다 | 내 AI 도구에 서버 주소만 등록 | [A. 공용 서버에 연결](#a-공용-서버에-연결-일반-사용자) |
| 서버를 **직접 띄워** 팀에 제공한다 | Docker 또는 Python으로 실행 | [B. 서버 띄우기](#b-서버-띄우기-운영자) |
| **나 혼자** Mac에서 쓴다 | 내 PC에서 실행, Chrome 쿠키 자동 사용 | [C. 로컬 모드](#c-로컬-모드-macos-혼자-사용) |

> 아래 `https://naverworks-mcp.example.com`은 예시입니다. 운영자에게 받은 실제 주소로 바꾸세요. (직접 띄웠다면 `http://localhost:9050`)

---

## A. 공용 서버에 연결 (일반 사용자)

### 1. AI 도구에 서버 주소 등록

주소는 **`/mcp/rpc`** 로 끝나야 하고, 쿠키나 헤더는 넣지 않습니다.

| 도구 | 등록 | 로그인 시작 |
|---|---|---|
| **Claude Code** | `claude mcp add --transport http --scope user naverworks <주소>/mcp/rpc` | `/mcp` → `naverworks` → Authenticate |
| **Cursor** | `~/.cursor/mcp.json`에 `"url": "<주소>/mcp/rpc"` | Settings → MCP → Login |
| **VS Code (Copilot)** | `mcp.json`에 `"type": "http"`, `"url": "<주소>/mcp/rpc"` | 서버 시작 시 Allow |
| **Opencode** | `opencode.json`에 `"type": "remote"`, `"url": "<주소>/mcp/rpc"` | `opencode mcp auth naverworks` |
| **Claude Desktop** | `npx -y mcp-remote <주소>/mcp/rpc` (Node.js 18 이상 필요) | 재시작하면 자동으로 열림 |

### 2. 브라우저에서 로그인

**네이버웍스 MCP 로그인** 페이지가 열리면 안내대로 네이버웍스에 로그인합니다. 그다음 개발자 도구 Network 탭에서 주소에 `/rd/`가 있는 요청을 **Copy as cURL**로 복사해 붙여넣고, **로그인 완료**를 누르면 됩니다. 이렇게 하면 쿠키와 조직 ID가 한 번에 설정됩니다. 로그인한 값은 AI 도구가 보관하고, 세션이 만료되면 로그인 페이지가 다시 열립니다.

→ 도구별 설정 예시와 로그인 단계: [client-setup.md](docs/client-setup.md)

### 3. 확인

- 도구 목록에 `naverworks` 도구(16개)가 보이면 연결된 것입니다.
- AI에게 **"내 네이버웍스 스페이스 목록 보여줘"** 라고 요청해 보세요.
- Claude Code에서는 `claude mcp list`를 실행했을 때 `✓ Connected`가 나와야 합니다.

→ 연결 후 무엇을 어떻게 요청하면 되는지: [client-setup.md](docs/client-setup.md)

> 로그인 페이지에 붙여넣는 값은 비밀번호와 같습니다. 다른 곳에 공유하거나 저장하지 마세요.

---

## B. 서버 띄우기 (운영자)

**Docker (권장)**:

```bash
git clone https://github.com/jak010/naverworks-project-mcp.git
cd naverworks-project-mcp
make docker-build && make docker-up   # 이미지 빌드 후 백그라운드 실행 (포트 9050)
```

**Python으로 직접 실행** (Python 3.10 이상):

```bash
make run              # .venv 생성 + 의존성 설치 + http://localhost:9050 실행
```

- 기본 설정은 `multi_user` 모드입니다. 서버는 쿠키를 저장하지 않고, 사용자마다 자기 쿠키로 요청합니다.
- 외부에 공개할 때는 HTTPS 리버스 프록시 뒤에 두고, OAuth 로그인 주소가 올바르게 만들어지도록 `PUBLIC_BASE_URL`(예: `https://naverworks-mcp.example.com`)을 설정하세요.
- 환경 변수 목록은 [deploy/.env.example](deploy/.env.example)에 있습니다.
- 제공 주소:
  - SSE: `<주소>/sse`
  - Streamable HTTP(Opencode): `<주소>/mcp/rpc`
  - API 문서: `<주소>/docs`
- 확인: `curl http://localhost:9050/health`

→ 자세히: [developer-guide.md](docs/developer-guide.md)

---

## C. 로컬 모드 (macOS, 혼자 사용)

```bash
git clone https://github.com/jak010/naverworks-project-mcp.git
cd naverworks-project-mcp
make setup            # 가상환경 + Chrome 로그인 세션에서 쿠키 추출 + 연결 테스트
```

AI 도구에는 stdio 방식으로 등록합니다. 아래 경로는 저장소의 실제 절대 경로(`pwd`로 확인)로 바꾸세요.

```bash
claude mcp add --scope user naverworks -- "$PWD/.venv/bin/python" "$PWD/apps/server.py"
```

→ 자세히: [client-setup.md](docs/client-setup.md#부록-로컬-모드-macos-혼자-사용)

---

## 문제가 생기면

| 증상 | 해결 |
|---|---|
| 로그인 창이 안 열림 / 도구가 안 보임 | 주소가 `/mcp/rpc`로 끝나는지 확인하고, 설정에 `headers`나 `"oauth": false`가 있으면 지운 뒤 AI 도구를 재시작하세요 |
| 사용 중 다시 로그인 요구 | 네이버웍스 세션이 만료되었습니다. 열리는 로그인 페이지에서 다시 로그인하세요 (Opencode는 `opencode mcp auth naverworks`) |

그 밖의 문제: [client-setup.md](docs/client-setup.md#4-문제-해결)
