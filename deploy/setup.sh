#!/usr/bin/env bash
set -e

# ==============================================================================
# NAVER WORKS Custom Server 원클릭 설치 및 환경 설정 스크립트
# ==============================================================================

# 이 스크립트는 deploy/ 에 있으며, 저장소 루트를 기준으로 동작합니다.
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT="$( cd "$DIR/.." && pwd )"
cd "$ROOT"
export PYTHONPATH="$ROOT/apps${PYTHONPATH:+:$PYTHONPATH}"

COOKIE_DIR="$HOME/.config/naverworks"
COOKIE_FILE="$COOKIE_DIR/proj_cookies.txt"
LOGIN_URL="https://project.worksmobile.com"

echo "=================================================================="
echo "🚀 NAVER WORKS FastAPI 서버 원클릭 설치 및 세팅을 시작합니다."
echo "=================================================================="

# 1. Python 환경 확인
echo ""
echo "📦 [1/4] Python 가상환경 및 의존성 패키지 설치 중..."

# 다른 PC에서 복사해 온 .venv 등 실행할 수 없는 가상환경은 다시 만든다
if [ -d ".venv" ] && ! .venv/bin/python -c "" 2>/dev/null; then
    echo "⚠️  .venv 가 손상되어 다시 만듭니다..."
    rm -rf .venv
fi

if command -v uv &> /dev/null; then
    if [ ! -d ".venv" ]; then
        uv venv .venv
    fi
    uv pip install --python .venv/bin/python -r deploy/requirements-dev.txt
else
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -r deploy/requirements-dev.txt
fi

echo "✅ Python 환경 세팅 완료!"

# 2. 쿠키 파일 검사 및 자동 추출
echo ""
echo "🔑 [2/4] 네이버웍스 로그인 쿠키 검사 중..."

mkdir -p "$COOKIE_DIR"

check_cookie_valid() {
    if [ -f "$COOKIE_FILE" ] && [ $(wc -c < "$COOKIE_FILE") -gt 200 ]; then
        return 0
    else
        return 1
    fi
}

extract_cookie() {
    .venv/bin/python -c "
from app.core import refresh_cookie_jar
ok = refresh_cookie_jar()
exit(0 if ok else 1)
" 2>/dev/null
}

if check_cookie_valid; then
    echo "✅ 기존에 저장된 쿠키 파일이 확인되었습니다: $COOKIE_FILE"
else
    echo "ℹ️  저장된 쿠키가 없거나 유효하지 않습니다. Chrome 브라우저에서 자동 추출을 시도합니다..."
    if extract_cookie && check_cookie_valid; then
        echo "✅ Chrome 키체인에서 쿠키를 자동으로 추출하여 저장했습니다!"
    else
        echo ""
        echo "⚠️  Chrome에서 네이버웍스 쿠키를 찾지 못했습니다."
        echo "🌐 브라우저를 열어 네이버웍스 로그인 페이지로 이동합니다..."
        open "$LOGIN_URL"

        echo ""
        echo "------------------------------------------------------------------"
        echo "👉 열린 Chrome 브라우저에서 네이버웍스에 로그인을 완료해 주세요."
        echo "👉 로그인이 완료되면 아래에서 [Enter] 키를 눌러주세요."
        echo "------------------------------------------------------------------"
        read -p "로그인 완료 후 [Enter]를 누르세요: " dummy

        echo "🔄 쿠키 추출 재시도 중..."
        if extract_cookie && check_cookie_valid; then
            echo "✅ 쿠키 추출 및 저장 성공: $COOKIE_FILE"
        else
            echo "❌ 여전히 쿠키를 추출하지 못했습니다."
            echo "   Chrome 브라우저에서 https://project.worksmobile.com 에 정상 로그인되었는지 확인 후 다시 실행해 주세요."
            exit 1
        fi
    fi
fi

# 3. 네이버웍스 API 실제 통신 검증
echo ""
echo "📡 [3/4] 네이버웍스 API 연결 테스트 중..."

TEST_RESULT=$(NAVERWORKS_AUTH_MODE=local .venv/bin/python -c "
from app.core import api_request
from app.config import DEFAULT_DOMAIN_ID
res = api_request('GET', f'/rd/{DEFAULT_DOMAIN_ID}/api/v1/spaces')
if res.get('status') == 200:
    spaces = res.get('data', [])
    count = len(spaces) if isinstance(spaces, list) else len(spaces.get('spaces', []))
    print(f'SUCCESS:{count}')
else:
    print(f'ERROR:{res.get(\"status\")}:{res.get(\"error\")}')
")

if [[ $TEST_RESULT == SUCCESS* ]]; then
    COUNT=$(echo "$TEST_RESULT" | cut -d':' -f2)
    echo "🎉 네이버웍스 API 연결 성공! (조회된 스페이스: ${COUNT}개)"
else
    echo "⚠️ API 연결 실패: $TEST_RESULT"
    echo "쿠키 세션이 만료되었을 수 있습니다. 브라우저에서 재로그인 후 deploy/setup.sh 를 다시 실행해 주세요."
    exit 1
fi

# 4. 완료 안내
echo ""
echo "=================================================================="
echo "✨ 모든 설치 및 세팅이 성공적으로 완료되었습니다!"
echo "=================================================================="
echo ""
echo "▶️ 서버 실행 명령어:"
echo "   deploy/run.sh   (또는 make run)"
echo ""
echo "📖 Swagger API 문서 (서버 실행 후 접속):"
echo "   http://localhost:9050/docs"
echo ""

