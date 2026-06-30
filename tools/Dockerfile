# 더미 API 서버 (:8000) — MCP 워크플로우 테스트용
FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 복사 → 레이어 캐시 활용
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드
COPY dummy_api.py .

EXPOSE 8000

# 컨테이너 외부 접근을 위해 0.0.0.0 바인딩
CMD ["uvicorn", "dummy_api:app", "--host", "0.0.0.0", "--port", "8000"]
