#!/usr/bin/env bash
# NAVER WORKS MCP 서버 백그라운드(데몬) 관리 스크립트
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$( cd "$DIR/.." && pwd )"
cd "$ROOT_DIR"

PID_FILE="$ROOT_DIR/server.pid"
LOG_FILE="$ROOT_DIR/server.log"

get_pid() {
    if [ -f "$PID_FILE" ]; then
        local pid
        pid=$(cat "$PID_FILE" 2>/dev/null || true)
        if [ -n "$pid" ] && ps -p "$pid" > /dev/null 2>&1; then
            echo "$pid"
            return 0
        fi
    fi
    local pids
    pids=$(pgrep -f "apps/main.py" | tr '\n' ' ' || true)
    echo "$pids" | awk '{print $1}'
}

start() {
    local pid
    pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo "⚠️  NAVER WORKS 서버가 이미 실행 중입니다 (PID: $pid)."
        echo "    상태 확인: ./deploy/daemon.sh status"
        echo "    로그 확인: ./deploy/daemon.sh logs"
        return 0
    fi

    echo "🚀 NAVER WORKS 서버를 백그라운드(데몬)로 시작합니다..."
    nohup "$ROOT_DIR/deploy/run.sh" > "$LOG_FILE" 2>&1 &
    local new_pid=$!
    echo "$new_pid" > "$PID_FILE"

    sleep 1.5
    if ps -p "$new_pid" > /dev/null 2>&1; then
        echo "✅ 서버가 정상적으로 시작되었습니다 (PID: $new_pid)."
        echo "   - 로그 파일: $LOG_FILE"
        echo "   - 헬스체크: http://127.0.0.1:9050/health"
    else
        echo "❌ 서버 시작에 실패했습니다. 로그를 확인하세요:"
        tail -n 20 "$LOG_FILE"
        exit 1
    fi
}

stop() {
    local pid
    pid=$(get_pid)
    if [ -z "$pid" ]; then
        echo "ℹ️  실행 중인 NAVER WORKS 서버가 없습니다."
        rm -f "$PID_FILE"
        return 0
    fi

    echo "🛑 NAVER WORKS 서버를 종료합니다 (PID: $pid)..."
    kill "$pid" 2>/dev/null || true

    for _ in {1..10}; do
        if ! ps -p "$pid" > /dev/null 2>&1; then
            break
        fi
        sleep 0.5
    done

    if ps -p "$pid" > /dev/null 2>&1; then
        echo "⚠️  프로세스가 종료되지 않아 강제 종료(SIGKILL)합니다..."
        kill -9 "$pid" 2>/dev/null || true
    fi

    pkill -f "apps/main.py" 2>/dev/null || true
    rm -f "$PID_FILE"
    echo "✅ 서버가 종료되었습니다."
}

status() {
    local pid
    pid=$(get_pid)
    if [ -n "$pid" ]; then
        echo "🟢 NAVER WORKS 서버 실행 중 (PID: $pid)"
        if command -v curl > /dev/null 2>&1; then
            local health
            health=$(curl -s -m 2 http://127.0.0.1:9050/health || true)
            echo "   헬스체크 응답: $health"
        fi
    else
        echo "🔴 NAVER WORKS 서버가 중지되어 있습니다."
    fi
}

logs() {
    if [ ! -f "$LOG_FILE" ]; then
        touch "$LOG_FILE"
    fi
    echo "📋 실시간 로그 출력 (종료하려면 Ctrl+C):"
    tail -f "$LOG_FILE"
}

case "${1:-status}" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        stop
        sleep 1
        start
        ;;
    status)
        status
        ;;
    logs)
        logs
        ;;
    *)
        echo "사용법: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac

