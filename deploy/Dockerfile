# 빌드 컨텍스트는 저장소 루트입니다:
#   docker build -f deploy/Dockerfile .
#   docker compose -f deploy/docker-compose.yml up -d
# 이미지에서 제외할 파일은 deploy/Dockerfile.dockerignore (BuildKit) 에 정의되어 있습니다.
FROM python:3.13-slim

WORKDIR /workspace

# 필수 시스템 패키지 설치 (curl: HEALTHCHECK 용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 파이썬 의존성 설치
COPY deploy/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스 복사
COPY apps/app ./app
COPY apps/main.py .

# 기본 환경 변수 설정
ENV PORT=9050
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

EXPOSE 9050

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# 서버 실행 (multi_user 모드 기본, 자동 재시작 없음)
CMD ["python", "main.py"]

