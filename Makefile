PY := .venv/bin/python
LIVE_COOKIE ?= $(HOME)/.config/naverworks/proj_cookies.txt
COMPOSE := docker compose -f deploy/docker-compose.yml

.PHONY: help setup dev run test test-live lint spaces projects docker-build docker-up docker-down clean start stop restart status logs daemon-start daemon-stop daemon-restart daemon-status daemon-logs playground

help:
	@echo "NAVER WORKS MCP 서버 명령어 모음:"
	@echo "  make setup        - 가상환경 + 개발 의존성 설치, Chrome 쿠키 연동, API 연결 확인 (macOS, deploy/setup.sh)"
	@echo "  make dev          - 가상환경 + 개발 의존성만 설치 (쿠키 연동 없음)"
	@echo "  make run          - HTTP 서버 전면 실행 (포그라운드, 기본 포트: 9050, deploy/run.sh)"
	@echo "  make start        - HTTP 서버 백그라운드(데몬) 실행 (deploy/daemon.sh start)"
	@echo "  make stop         - 백그라운드 서버 종료 (deploy/daemon.sh stop)"
	@echo "  make restart      - 백그라운드 서버 재시작 (deploy/daemon.sh restart)"
	@echo "  make status       - 백그라운드 서버 상태 및 헬스체크 (deploy/daemon.sh status)"
	@echo "  make logs         - 백그라운드 서버 실시간 로그 확인 (deploy/daemon.sh logs)"
	@echo "  make test         - 테스트 실행 (네이버웍스는 mock, 실제 요청 없음)"
	@echo "  make test-live    - 실제 네이버웍스 CRUD 테스트 ([MCP-TEST] 리소스 생성 후 삭제, LIVE_COOKIE=쿠키파일)"
	@echo "  make lint         - pyflakes 정적 검사"
	@echo "  make spaces       - CLI로 스페이스 목록 조회 (local 모드)"
	@echo "  make projects SPACE_ID=<id> - CLI로 프로젝트 목록 조회"
	@echo "  make docker-build - Docker 이미지 빌드"
	@echo "  make docker-up    - Docker Compose로 백그라운드 실행 (multi_user 모드)"
	@echo "  make docker-down  - Docker 컨테이너 종료"
	@echo "  make clean        - 파이썬 캐시 및 임시 파일 정리"


setup:
	deploy/setup.sh

dev:
	@if [ -d .venv ] && ! $(PY) -c "" 2>/dev/null; then echo "손상된 .venv 재생성"; rm -rf .venv; fi
	@if [ ! -d .venv ]; then uv venv .venv; fi
	uv pip install --python $(PY) -r deploy/requirements-dev.txt

run:
	deploy/run.sh

start:
	deploy/daemon.sh start

stop:
	deploy/daemon.sh stop

restart:
	deploy/daemon.sh restart

status:
	deploy/daemon.sh status

logs:
	deploy/daemon.sh logs

daemon-start: start
daemon-stop: stop
daemon-restart: restart
daemon-status: status
daemon-logs: logs


test:
	$(PY) -m pytest

test-live:
	NAVERWORKS_LIVE_COOKIE_PATH="$(LIVE_COOKIE)" $(PY) -m pytest tests/test_live_crud.py -v

lint:
	$(PY) -m pyflakes apps tests playground

playground:
	$(PY) playground/test_api_runner.py


spaces:
	$(PY) apps/cli.py spaces

projects:
	@if [ -z "$(SPACE_ID)" ]; then \
		echo "사용법: make projects SPACE_ID=<space_id>"; \
	else \
		$(PY) apps/cli.py projects $(SPACE_ID); \
	fi

docker-build:
	$(COMPOSE) build

docker-up:
	$(COMPOSE) up -d

docker-down:
	$(COMPOSE) down

clean:
	find . -path ./.venv -prune -o -type d -name "__pycache__" -exec rm -rf {} +
	find . -path ./.venv -prune -o -type f -name "*.pyc" -exec rm -f {} +
	rm -rf .pytest_cache
