#!/usr/bin/env bash
# 개발용 간편 실행 스크립트 (코드 변경 시 자동 재시작)
set -e

# 이 스크립트는 deploy/ 에 있으며, 저장소 루트를 기준으로 동작합니다.
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR/.."

# 다른 PC에서 복사해 온 .venv 등 실행할 수 없는 가상환경은 다시 만든다
if [ -d ".venv" ] && ! .venv/bin/python -c "" 2>/dev/null; then
    echo "⚠️  .venv 가 손상되어 다시 만듭니다..."
    rm -rf .venv
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    if command -v uv &> /dev/null; then
        uv venv .venv
        uv pip install --python .venv/bin/python -r deploy/requirements.txt
    else
        python3 -m venv .venv
        .venv/bin/pip install -r deploy/requirements.txt
    fi
fi

echo "Starting NAVER WORKS FastAPI Server..."
RELOAD="${RELOAD:-true}" exec .venv/bin/python apps/main.py
