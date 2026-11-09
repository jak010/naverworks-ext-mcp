import os

BASE_URL = os.getenv("NAVERWORKS_BASE_URL", "https://project.worksmobile.com")
MAIL_BASE_URL = os.getenv("NAVERWORKS_MAIL_BASE_URL", "https://mail.worksmobile.com")
# 조직 ID: 기본값 없음. ID·응답·로그인한 웹 페이지에서 사용자별로 알아냅니다. 알아낼 수 없을 때만 쓰는 선택 설정
DEFAULT_DOMAIN_ID = os.getenv("NAVERWORKS_DOMAIN_ID", "").strip()
DEFAULT_INSTANCE_CODE = os.getenv("NAVERWORKS_INSTANCE_CODE", "24101")
COOKIE_JAR_PATH = os.path.expanduser(
    os.getenv("NAVERWORKS_COOKIE_JAR_PATH", "~/.config/naverworks/proj_cookies.txt")
)
# 인증 모드
#  - multi_user (기본값): 익명 다중 사용자 서비스. 각 사용자가 요청/세션마다 자신의 쿠키를 직접 제공해야 하며,
#    서버 호스트의 자격 증명(환경 변수 쿠키, 로컬 쿠키 파일, Chrome 키체인, 브라우저 로그인)과
#    서버 로컬 파일 경로 기반 쿠키 입력(X-Naverworks-Cookie-Path 등)은 사용하지 않습니다.
#  - local: 본인 PC에서 혼자 쓰는 모드 (stdio server.py / cli.py의 기본값).
#    환경 변수 쿠키와 로컬 쿠키 파일 fallback, 쿠키 파일 경로 입력, 브라우저 로그인을 허용합니다.
# 알 수 없는 값은 안전하게 multi_user로 취급합니다.
AUTH_MODE = os.getenv("NAVERWORKS_AUTH_MODE", "multi_user")


def is_local_mode() -> bool:
    return (AUTH_MODE or "").strip().lower() == "local"

PORT = int(os.getenv("PORT", 9050))

# MCP 표준 OAuth 브라우저 로그인 (쿠키 없이 /mcp/rpc 접속 시 401 → 클라이언트가 /oauth/authorize 로그인 페이지를 엶)
# 끄려면 NAVERWORKS_OAUTH_ENABLED=false
OAUTH_ENABLED = os.getenv("NAVERWORKS_OAUTH_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}
# 리버스 프록시 뒤에서 외부 주소가 다를 때 지정 (예: https://naverworks-mcp.example.com)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()


def _csv(value: str) -> list:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


# 바인드 호스트: local 모드는 서버가 사용자 본인의 쿠키를 자동 사용하므로 기본적으로 루프백에만 바인드합니다.
HOST = os.getenv("HOST") or ("127.0.0.1" if is_local_mode() else "0.0.0.0")

# CORS 허용 Origin (쉼표 구분). 기본값은 비어 있음 = 교차 출처 브라우저 요청 불허.
# 대시보드(/dashboard)와 Swagger(/docs)는 같은 출처라 CORS가 필요 없습니다.
CORS_ALLOW_ORIGINS = _csv(os.getenv("CORS_ALLOW_ORIGINS", ""))

# local 모드에서 허용할 Host/Origin 호스트명 (DNS rebinding 및 악성 웹페이지의 localhost 호출 차단)
LOCAL_ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1"} | set(_csv(os.getenv("LOCAL_ALLOWED_HOSTS", "")))

