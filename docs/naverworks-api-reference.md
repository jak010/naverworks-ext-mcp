# NAVER WORKS Spaces & Project API Guide

NAVER WORKS Project 웹 서비스의 **스페이스(Space)**, **프로젝트(Project)** 및 **작업(Task)** 관련 Internal API 가이드입니다.

> 공개 API가 아닌 웹 서비스 내부 API이므로 예고 없이 바뀔 수 있습니다. ✅ 표시는 2026-11-07 실제 API로 확인한 동작입니다.

---

## 1. 개요 및 인증 (Overview & Auth)

- **Base URL**: `https://project.worksmobile.com`
- **인증 방식**: 브라우저 세션 쿠키를 `Cookie` 요청 헤더로 전달 (핵심 쿠키: `WORKS_SES`, `NEO_SES` — 둘 다 HttpOnly)
  - local 모드에서는 Netscape 형식 쿠키 파일 `~/.config/naverworks/proj_cookies.txt`에 저장해 사용
- **프로토콜**: HTTP/1.1 권장 (`--http1.1`, HTTP/2 framing 이슈 방지)
- **OAuth 지원 여부**: OAuth Access Token 미지원 (`401 Unauthorized`), 브라우저 세션 쿠키 필수

### 1.1 인증 미설정 시 처리

이 서버를 통해 호출할 때 쿠키를 얻는 방법은 서버의 인증 모드에 따라 다릅니다.

- **multi_user 모드 (공용 서버, 기본값)**: 각 사용자가 자신의 쿠키를 요청 헤더(`X-Naverworks-Cookie`)로 전달합니다. 서버는 쿠키를 추출하지 않습니다. → [client-setup.md](client-setup.md#2-브라우저에서-로그인)
- **local 모드 (본인 PC)**: Chrome 로그인 세션에서 쿠키를 추출해 `~/.config/naverworks/proj_cookies.txt`에 저장합니다.
  ```bash
  .venv/bin/python apps/cli.py refresh-cookie   # Chrome 세션에서 재추출
  .venv/bin/python apps/cli.py login            # Chrome 세션도 만료된 경우: 브라우저 로그인 후 자동 저장
  ```
  추출 로직은 `apps/app/core/cookie.py`의 `refresh_cookie_jar()`에 있습니다. (macOS 키체인 `Chrome Safe Storage` 사용)

---

## 2. API 엔드포인트 요약 (Endpoints)

| 대상 | 기능 | Method | Path |
|---|---|---|---|
| **스페이스** | 전체 스페이스 목록 조회 | `GET` | `/rd/{domainId}/api/v1/spaces` |
| **스페이스** | 신규 스페이스 생성 | `POST` | `/rd/{domainId}/api/v1/spaces` |
| **스페이스** | 단일 스페이스 상세 조회 | `GET` | `/rd/{domainId}/api/v1/spaces/{spaceId}` |
| **스페이스** | 스페이스 삭제 | `DELETE` | `/rd/{domainId}/api/v1/spaces/{spaceId}` |
| **프로젝트** | 스페이스 소속 프로젝트 목록 조회 | `GET` | `/rd/{domainId}/api/v1/projects?spaceId={spaceId}` |
| **프로젝트** | 신규 프로젝트 생성 | `POST` | `/rd/{domainId}/api/v1/projects` |
| **프로젝트** | 프로젝트 상세 정보 조회 | `GET` | `/rl/{instanceCode}/api/v1/projects/{projectId}` |
| **프로젝트** | 프로젝트 삭제 | `DELETE` | `/rl/{instanceCode}/api/v1/projects/{projectId}` |
| **작업(Task)** | 신규 작업 생성 | `POST` | `/rd/{domainId}/api/v1/tasks` |
| **작업(Task)** | 단일 작업 상세 조회 | `GET` | `/rd/{domainId}/api/v1/tasks/{taskId}` |
| **작업(Task)** | 작업 본문(Content) 수정 | `POST` | `/rd/{domainId}/api/v1/tasks/{taskId}/content` |
| **작업(Task)** | 단일 작업 삭제 | `DELETE` | `/rd/{domainId}/api/v1/tasks/{taskId}` |
| **작업(Task)** | 프로젝트 소속 작업 전체 조회 | `GET` | `/rd/{domainId}/api/v1/tasks?projectId={projectId}` |

> [!IMPORTANT]
> - **스페이스/프로젝트/작업 생성, 조회, 수정, 삭제**: Path prefix로 **`/rd/{domainId}/`** 사용 (`domainId` 예: `300098158`)
> - **프로젝트 상세 조회 및 프로젝트 삭제**: Path prefix로 **`/rl/{instanceCode}/`** 사용 (`rl` 예: `24101`, 스페이스/프로젝트 조회 결과의 `rl` 값)

### 2.1 식별자와 경로 값 ✅

- **모든 ID에 domainId가 포함됩니다**: `s-{domainId}-{uuid}` (스페이스), `p-{domainId}-{uuid}` (프로젝트), `t-{domainId}-{uuid}` (작업)
- **domainId가 틀리면 오류가 아니라 빈 결과**가 옵니다: 다른 값으로 `GET /rd/{domainId}/api/v1/spaces` 를 호출하면 `200` + `[]`
- 스페이스·프로젝트 응답에는 `domainId`, `tenantId`(= domainId), `rl` 필드가 있습니다.
- 프로젝트 상세 조회(`GET /rl/{instanceCode}/...`)는 `instanceCode` 값이 달라도 조회됩니다. (쓰기 요청에는 조회 결과의 `rl` 값을 사용하세요)

---

## 3. 스페이스 API (Spaces API)

### 3.1 신규 스페이스 생성 (POST `/rd/{domainId}/api/v1/spaces`)
- **Headers**: `Content-Type: application/json`, `Cookie: ...`
- **Request Body**:
```json
{
  "spaceName": "신규 스페이스",
  "spaceColor": "#4694e5",
  "spaceDescription": {
    "htmlText": "",
    "plainText": "",
    "mentionedUserIds": [],
    "inlineImages": [],
    "editorVersion": null
  }
}
```
*컬러 팔레트: `#f25050`, `#ed7200`, `#f5c449`, `#5da451`, `#449fab`, `#4694e5`, `#5163c7`, `#b274df`, `#f06595`, `#906958`, `#7d8083`, `#434547`*

- **Response Key Fields**: `spaceId`, `spaceName`, `rl`, `domainId`, `tenantId`, `spaceMasterId`, `rootFolder.children`

### 3.2 스페이스 목록 / 상세 조회 / 삭제
- **전체 목록**: `GET /rd/{domainId}/api/v1/spaces`
- **단일 상세**: `GET /rd/{domainId}/api/v1/spaces/{spaceId}` (소속 프로젝트 목록은 `rootFolder.children` 내 `FolderChildProject` 확인)
- **삭제**: `DELETE /rd/{domainId}/api/v1/spaces/{spaceId}`

---

## 4. 프로젝트 API (Projects API)

### 4.1 신규 프로젝트 생성 (POST `/rd/{domainId}/api/v1/projects`)
- **Request Body**:
```json
{
  "spaceId": "s-300098158-4400b350-7c86-40db-b5cb-9813fcbfac1a",
  "projectName": "신규 프로젝트",
  "projectColor": "#ed7200",
  "projectType": "OPEN",
  "spaceProjectParameter": null
}
```
*특정 폴더 하위에 생성 시: `"spaceProjectParameter": { "parentFolderId": "fd-{uuid}" }`*

- **Response Key Fields**: `projectId`, `projectName`, `rl`, `projectViews`, `customFields`

### 4.2 프로젝트 목록 / 상세 조회 / 삭제
- **스페이스 소속 목록**: `GET /rd/{domainId}/api/v1/projects?spaceId={spaceId}` → 프로젝트 객체 배열 ✅
- **상세 조회**: `GET /rl/{instanceCode}/api/v1/projects/{projectId}`
- **프로젝트 삭제**: `DELETE /rl/{instanceCode}/api/v1/projects/{projectId}`

---

## 5. 작업 API (Tasks API)

### 5.1 신규 작업 생성 (POST `/rd/{domainId}/api/v1/tasks`)
- **Request Body**:
```json
{
  "projectId": "p-300098158-56a66c58-c478-400a-9698-2f0199bb9b07",
  "title": "신규 작업 제목",
  "taskStatusType": "OPEN",
  "content": { "htmlText": "", "mentionedUserIds": [], "inlineImages": [] },
  "assigneesIds": [],
  "projectTaskParameters": [
    {
      "taggedProjectKey": {
        "rl": "24101",
        "domainId": "300098158",
        "projectId": "p-300098158-56a66c58-c478-400a-9698-2f0199bb9b07"
      }
    }
  ],
  "parentTaskId": null
}
```
> `taggedProjectKey`는 필수(생략 시 400 `INVALID_PARAMETER`)입니다. `actionUserId`는 생략 가능하며, 값을 넣어도 무시되고 생성자는 요청 쿠키의 세션 사용자로 결정됩니다. (2026-11-07 실제 API 검증)
*하위 작업 생성 시: `"parentTaskId": "t-{domainId}-{uuid}"` 지정*

- **Response Key Fields**: `taskId`, `title`, `status`, `mainProjectId`, `parentTaskId`
- 생성자는 요청 쿠키의 세션 사용자입니다 ✅

### 5.2 작업 상세 조회 / 본문 수정 / 삭제 / 프로젝트 목록 조회
- **단일 작업 상세**: `GET /rd/{domainId}/api/v1/tasks/{taskId}`
  - **Response** ✅: 작업 객체가 한 번 감싸져 있습니다 → `{"task": {...}, "relatedUserIds": [...]}`
  - `task` 주요 필드: `taskId`, `title`, `status.taskStatusType`, `content.plainText` / `content.htmlText`, `parentTaskId`, `subTaskIds`, `isParentTask`, `due`, `created`, `modified`
- **작업 본문(Content) 수정**: `POST /rd/{domainId}/api/v1/tasks/{taskId}/content`
  - **Request Body**: `{"content": {"htmlText": "<p>내용</p>", "mentionedUserIds": [], "inlineImages": []}}`
- **단일 작업 삭제**: `DELETE /rd/{domainId}/api/v1/tasks/{taskId}`
- **프로젝트 전체 작업 목록**: `GET /rd/{domainId}/api/v1/tasks?projectId={projectId}`
  - **Response** ✅: `{"projectTasks": [...], "relatedUserIds": [...]}`
  - 목록 항목의 `status`는 객체(`{"taskStatusType": "OPEN", "lastModified": ...}`), `content`는 `htmlText`·`plainText`를 가진 객체입니다.

---

## 6. 오류 처리 요약 (Troubleshooting)

| 상태 코드 | 원인 | 해결 방안 |
|---|---|---|
| `400 Bad Request` | 스페이스/프로젝트생성/태스크 API에 `/rl/` prefix 사용 | 반드시 `/rd/{domainId}/` prefix 사용 |
| `400 INVALID_PARAMETER` | 작업 생성 시 `projectTaskParameters`가 비어 있음 ✅ | `taggedProjectKey` 포함 |
| `401 Unauthorized` | 쿠키 누락 또는 만료 (OAuth 토큰 사용 시 포함) | 새로 로그인한 세션의 쿠키 사용 |
| `200` + 빈 배열 | `domainId`가 사용자의 조직과 다름 ✅ | ID에 포함된 `domainId` 확인 (2.1 참고) |
| `404 Not Found` | 존재하지 않는 식별자 | `spaceId`, `projectId`, `taskId` 확인 |
| `500 Server Error` | 필수 파라미터 누락 | 태스크: `projectTaskParameters` 및 `taggedProjectKey` 확인 / 프로젝트: `spaceId`, `projectName`, `projectColor`, `projectType` 확인 |
