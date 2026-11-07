import os
import base64
import binascii
import sys
import glob
import time
import sqlite3
import hashlib
import threading
import subprocess
from typing import Optional
from app import config
from app.core.auth_context import (
    get_current_user_cookie,
    get_current_cookie_source,
    get_current_cookie_path,
)

_cookie_lock = threading.Lock()
# 로컬 쿠키 파일 파싱 결과 캐시: (경로, mtime, 쿠키 헤더)
_jar_cache: Optional[tuple] = None

MIN_COOKIE_LENGTH = 20


def _looks_valid(cookie: Optional[str]) -> bool:
    return bool(cookie and len(cookie.strip()) > MIN_COOKIE_LENGTH)


def read_local_cookie_jar() -> Optional[str]:
    """서버 로컬 쿠키 파일(COOKIE_JAR_PATH)을 읽어 Cookie 헤더로 반환합니다. 파일 변경 시에만 다시 파싱합니다."""
    global _jar_cache
    path = config.COOKIE_JAR_PATH
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    cached = _jar_cache
    if cached and cached[0] == path and cached[1] == mtime:
        return cached[2]
    header = read_cookie_file(path)
    _jar_cache = (path, mtime, header)
    return header


def is_cookie_valid() -> bool:
    """현재 요청 컨텍스트에서 실제로 사용될 쿠키(get_cookie_header)가 유효한지 확인합니다."""
    return _looks_valid(get_cookie_header())


def _local_jar_valid() -> bool:
    """Chrome에서 추출해 저장한 로컬 쿠키 파일이 유효한지 확인합니다. (인증 모드와 무관)"""
    return _looks_valid(read_local_cookie_jar())


def notify_macos(title: str, message: str) -> None:
    """Send desktop notification on macOS if available."""
    if sys.platform == "darwin":
        try:
            safe_title = title.replace('"', '\\"')
            safe_msg = message.replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'display notification "{safe_msg}" with title "{safe_title}"'],
                capture_output=True,
                timeout=3.0
            )
        except Exception:
            pass


def open_browser(url: str = "https://project.worksmobile.com") -> bool:
    """Open login URL in Google Chrome or default browser."""
    try:
        if sys.platform == "darwin":
            res = subprocess.run(["open", "-a", "Google Chrome", url], capture_output=True)
            if res.returncode != 0:
                subprocess.run(["open", url], capture_output=True)
            return True
        else:
            import webbrowser
            webbrowser.open(url)
            return True
    except Exception as e:
        sys.stderr.write(f"Failed to open browser: {e}\n")
        return False


def login_via_browser(timeout_seconds: int = 90, force: bool = False) -> dict:
    """
    브라우저를 열어 네이버웍스 로그인을 유도하고, 완료 시 Chrome 쿠키를 자동 감지/복호화하여 저장합니다.
    """
    if not force:
        # 1. Chrome에 이미 로그인 세션이 남아있는지 우선 검사 (브라우저 안 띄우고도 즉시 해결 가능한지 점검)
        if refresh_cookie_jar() and _local_jar_valid():
            return {
                "success": True,
                "message": f"Chrome에 이미 존재하는 네이버웍스 세션을 성공적으로 감지하여 쿠키를 저장했습니다: {config.COOKIE_JAR_PATH}",
                "cookiePath": config.COOKIE_JAR_PATH
            }

    # 2. 브라우저 오픈 및 macOS 알림
    sys.stderr.write("🌐 [MCP Auth] 네이버웍스 브라우저 로그인을 시작합니다...\n")
    notify_macos("NAVER WORKS MCP", "네이버웍스 로그인 창이 열렸습니다. 로그인 완료 시 자동으로 MCP에 연동됩니다.")
    open_browser("https://project.worksmobile.com")

    # 3. 사용자 로그인 완료 대기 (Chrome 쿠키 DB 주기적 폴링)
    start_time = time.time()
    poll_interval = 2.0

    while (time.time() - start_time) < timeout_seconds:
        time.sleep(poll_interval)
        if refresh_cookie_jar() and _local_jar_valid():
            elapsed = round(time.time() - start_time, 1)
            sys.stderr.write(f"✅ [MCP Auth] 로그인 감지 완료 ({elapsed}초 소요)\n")
            notify_macos("NAVER WORKS MCP", "네이버웍스 로그인 및 쿠키 연동이 완료되었습니다!")
            return {
                "success": True,
                "message": f"네이버웍스 브라우저 로그인이 감지되어 쿠키가 성공적으로 저장되었습니다: {config.COOKIE_JAR_PATH}",
                "cookiePath": config.COOKIE_JAR_PATH,
                "elapsedSeconds": elapsed
            }

    return {
        "success": False,
        "message": f"{timeout_seconds}초 동안 네이버웍스 로그인이 감지되지 않았습니다. 브라우저에서 로그인을 완료한 후 다시 시도해주세요.",
        "cookiePath": config.COOKIE_JAR_PATH
    }


def ensure_cookie_jar(allow_browser_login: bool = False) -> bool:
    """Ensure cookie jar exists and is populated from Chrome Safe Storage if needed."""
    if is_cookie_valid():
        return True
    if refresh_cookie_jar() and is_cookie_valid():
        return True
    if allow_browser_login:
        res = login_via_browser(timeout_seconds=60)
        return res.get("success", False)
    return False


def refresh_cookie_jar() -> bool:
    """Extract and decrypt NAVER WORKS cookies from Chrome into proj_cookies.txt."""
    global _jar_cache
    with _cookie_lock:
        os.makedirs(os.path.dirname(config.COOKIE_JAR_PATH), exist_ok=True)
        try:
            pw = subprocess.check_output([
                "security", "find-generic-password", "-w",
                "-s", "Chrome Safe Storage", "-a", "Chrome"
            ]).rstrip(b"\n")
        except Exception as e:
            sys.stderr.write(f"Keychain error: {e}\n")
            return False

        key = hashlib.pbkdf2_hmac("sha1", pw, b"saltysalt", 1003, 16)
        iv = b" " * 16

        def decrypt(val: bytes, strip_prefix: bool) -> Optional[str]:
            if not val or val[:3] != b"v10":
                return None
            p = subprocess.run(
                ["openssl", "enc", "-aes-128-cbc", "-d",
                 "-K", key.hex(), "-iv", iv.hex(), "-nopad"],
                input=val[3:], capture_output=True
            )
            if p.returncode != 0 or not p.stdout:
                return None
            pt = p.stdout
            pad = pt[-1]
            if 1 <= pad <= 16 and pt.endswith(bytes([pad]) * pad):
                pt = pt[:-pad]
            if strip_prefix and len(pt) > 32:
                pt = pt[32:]
            return pt.decode("utf-8", "replace")

        chrome_base = os.path.expanduser("~/Library/Application Support/Google/Chrome")
        candidates = [
            p for p in glob.glob(f"{chrome_base}/*/Cookies") + [f"{chrome_base}/Default/Cookies"]
            if os.path.exists(p)
        ]
        if not candidates:
            return False

        best_db = None
        max_count = 0
        for db_path in candidates:
            try:
                con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
                cnt = con.execute(
                    "select count(*) from cookies where host_key like '%worksmobile.com'"
                ).fetchone()[0]
                con.close()
                if cnt > max_count:
                    max_count = cnt
                    best_db = db_path
            except Exception:
                pass

        if not best_db:
            return False

        con = sqlite3.connect(f"file:{best_db}?mode=ro", uri=True)
        meta = dict(con.execute("select key, value from meta").fetchall())
        strip_prefix = int(meta.get("version", "0")) >= 24

        rows = con.execute(
            "select host_key, is_secure, path, expires_utc, name, encrypted_value "
            "from cookies where host_key like '%worksmobile.com' order by host_key, name"
        ).fetchall()
        con.close()

        lines = ["# Netscape HTTP Cookie File"]
        seen = set()
        for host, secure, path, expires, name, enc in rows:
            if (host, name) in seen:
                continue
            val = decrypt(enc, strip_prefix)
            if val is None or any(ord(c) < 0x20 or ord(c) == 0x7f for c in val):
                continue
            seen.add((host, name))
            exp = int(expires / 1000000 - 11644473600) if expires else 2147483647
            if exp <= 0:
                exp = 2147483647
            include_sub = "TRUE" if host.startswith(".") else "FALSE"
            sec = "TRUE" if secure else "FALSE"
            lines.append("\t".join([
                host, include_sub, path or "/", sec, str(exp), name, val
            ]))

        with open(config.COOKIE_JAR_PATH, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.chmod(config.COOKIE_JAR_PATH, 0o600)
        _jar_cache = None  # 캐시 무효화
        return True


def read_cookie_file(path: str) -> Optional[str]:
    """Netscape 쿠키 파일 또는 key=value 형식의 쿠키 텍스트 파일을 파싱하여 Cookie 헤더 문자열로 반환합니다."""
    if not path or not path.strip():
        return None
    expanded_path = os.path.expanduser(path.strip())
    if not os.path.exists(expanded_path):
        return None

    cookie_pairs = []
    try:
        with open(expanded_path, "r", encoding="utf-8") as f:
            for line in f:
                line_str = line.strip()
                if line_str.startswith("#") or not line_str:
                    continue
                parts = line_str.split("\t")
                if len(parts) >= 7:
                    name = parts[5].strip()
                    val = parts[6].strip()
                    if name and val:
                        cookie_pairs.append(f"{name}={val}")
                elif "=" in line_str:
                    for item in line_str.split(";"):
                        item = item.strip()
                        if "=" in item:
                            cookie_pairs.append(item)
        return "; ".join(cookie_pairs) if cookie_pairs else None
    except Exception:
        return None


def get_cookie_header() -> str:
    """현재 요청에 사용할 Cookie 헤더 문자열을 반환합니다.

    1) 현재 요청/세션 사용자의 쿠키 (ContextVar, 사용자별 격리) — 모든 모드
    2) NAVERWORKS_COOKIE 환경 변수                              — local 모드 전용
    3) NAVERWORKS_COOKIE_PATH 환경 변수의 쿠키 파일             — local 모드 전용
    4) 로컬 쿠키 파일(COOKIE_JAR_PATH)                          — local 모드 전용

    multi_user 모드에서는 사용자가 쿠키를 제공하지 않으면 빈 문자열을 반환하며,
    서버 호스트의 자격 증명으로 절대 대체하지 않습니다."""
    user_cookie = get_current_user_cookie()
    if user_cookie and user_cookie.strip():
        return user_cookie.strip()

    if not config.is_local_mode():
        return ""

    env_cookie = os.getenv("NAVERWORKS_COOKIE")
    if env_cookie and env_cookie.strip():
        return env_cookie.strip()

    env_cookie_path = os.getenv("NAVERWORKS_COOKIE_PATH")
    if env_cookie_path and env_cookie_path.strip():
        res = read_cookie_file(env_cookie_path.strip())
        if res:
            return res

    # setup.sh / login_naverworks / refresh-cookie가 저장한 쿠키 파일
    jar_cookie = read_local_cookie_jar()
    if jar_cookie:
        return jar_cookie

    return ""


def read_user_cookie_path(path: Optional[str]) -> Optional[str]:
    """사용자가 '쿠키 파일 경로'로 전달한 값(헤더/쿼리/set_user_cookie)을 읽습니다.
    경로는 서버 호스트의 파일을 가리키므로 local 모드에서만 허용합니다.
    (multi_user 모드에서 허용하면 익명 사용자가 서버의 쿠키 파일 등 임의 파일을 읽어 사용할 수 있음)"""
    if not path or not config.is_local_mode():
        return None
    return read_cookie_file(path)


def describe_cookie_source() -> dict:
    """get_cookie_header()가 실제로 사용하는 쿠키의 출처와 파일 경로를 반환합니다. (get_auth_status용)"""
    if (get_current_user_cookie() or "").strip():
        return {"source": get_current_cookie_source(), "path": get_current_cookie_path()}
    if not config.is_local_mode():
        return {"source": "none", "path": None}
    if (os.getenv("NAVERWORKS_COOKIE") or "").strip():
        return {"source": "env_cookie", "path": None}
    env_path = (os.getenv("NAVERWORKS_COOKIE_PATH") or "").strip()
    if env_path and read_cookie_file(env_path):
        return {"source": "env_cookie_path", "path": os.path.expanduser(env_path)}
    if read_local_cookie_jar():
        return {"source": "local_cookie_jar", "path": config.COOKIE_JAR_PATH}
    return {"source": "none", "path": None}


# ------------------------------------------------------------------------------
# OAuth access token <-> 쿠키
# 쿠키 원문에는 공백과 ';'이 있어 Bearer 토큰 형식(RFC 6750 b64token)에 맞지 않으므로
# base64url(패딩 없음)로 감싸 접두어를 붙여 발급합니다.
# ------------------------------------------------------------------------------

ACCESS_TOKEN_PREFIX = "nwc_"


def encode_access_token(cookie: str) -> str:
    raw = base64.urlsafe_b64encode(cookie.encode("utf-8")).rstrip(b"=").decode("ascii")
    return ACCESS_TOKEN_PREFIX + raw


def decode_access_token(token: str) -> Optional[str]:
    """`nwc_` 토큰이면 쿠키 문자열로 복원합니다. 형식이 아니거나 손상되었으면 None."""
    if not token or not token.startswith(ACCESS_TOKEN_PREFIX):
        return None
    body = token[len(ACCESS_TOKEN_PREFIX):]
    try:
        cookie = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8")
    except (binascii.Error, ValueError, UnicodeDecodeError):
        return None
    cookie = cookie.strip()
    return cookie if "=" in cookie else None
