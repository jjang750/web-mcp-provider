# MCP Provider — MCP HTTP 서버 + 관리 UI 공용 이미지
# 빌드 컨텍스트: app/  (docker compose build 시 자동)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 의존성 먼저 설치(레이어 캐시)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 소스
COPY . /app

# 런타임 산출물(DB)은 볼륨(/data)에 저장 — 코드와 분리
ENV MCP_DB_PATH=/data/mcp_provider.db
RUN mkdir -p /data

# 기본 명령은 compose 에서 서비스별로 override
EXPOSE 9900 9090
CMD ["python", "-m", "backend.mcp_http_server"]
