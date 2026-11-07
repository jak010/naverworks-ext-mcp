# 문서 목록

| 문서 | 대상 | 내용 |
|---|---|---|
| [client-setup/](client-setup/README.md) | **사용자** | 내 PC의 AI 도구를 MCP 서버에 연결하기 — **최종 체크리스트**, 보안 수칙, 문제 해결 |
| ├ [01-get-cookie.md](client-setup/01-get-cookie.md) | 사용자 | 브라우저에서 내 네이버웍스 쿠키 복사하기 |
| ├ [02-client-config.md](client-setup/02-client-config.md) | 사용자 | AI 도구별 등록 방법 (Claude Desktop, Claude Code, Cursor, VS Code, Opencode) |
| ├ [03-local-mode.md](client-setup/03-local-mode.md) | 사용자 (혼자 사용) | 내 PC에서 서버를 직접 실행하기 (로컬 모드) |
| ├ [04-opencode.md](client-setup/04-opencode.md) | 사용자 (Opencode) | Opencode 설정 — `/mcp/rpc` 주소, **브라우저 로그인(OAuth, 권장)** 또는 쿠키 파일 경로(`{file:…}`), 쿠키 교체, 문제 해결 |
| └ [mcp_config_example.json](client-setup/mcp_config_example.json) | 사용자 | `url` + `headers` 형식 설정 예시 (Cursor 등) |
| [llm-integration-guide.md](llm-integration-guide.md) | 개발자·운영자 | 서버 실행·인증 모드, MCP 엔드포인트, OAuth 브라우저 로그인, 쿠키 전달 방식, 그 밖의 클라이언트, 코드에서 직접 호출 |
| [naverworks-project-api-v2.md](naverworks-project-api-v2.md) | 개발자 | 네이버웍스 Project 내부 API 명세 (실제 API 검증 결과 포함) |
