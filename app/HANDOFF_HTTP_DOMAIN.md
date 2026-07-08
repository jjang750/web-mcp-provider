# HANDOFF — MCP 서버 도메인(HTTP/HTTPS) 노출

## 요약
- 기존 stdio 서버(`backend/mcp_server.py`)를 **HTTP(streamable_http)** 로 노출하는
  별도 진입점 `backend/mcp_http_server.py` 추가.
- 툴 빌드·실행 로직은 stdio 와 **동일 코드 재사용**(전송 계층만 교체).
- 인증: `Authorization: Bearer <MCP_AUTH_TOKEN>`. TLS: uvicorn이 인증서 직접 로드(같은 도메인/HTTPS).
- 검증 완료: `initialize`+`tools/list` 3개 노출, 무/오토큰 401, healthz 200, HTTPS 기동 OK.

## 추가/변경 파일
- `backend/mcp_http_server.py` — streamable_http 서버 (신규)
- `PLAN_HTTP_DOMAIN.md` — 플랜 (신규)
- `HANDOFF_HTTP_DOMAIN.md` — 본 문서 (신규)
- 기존 `backend/mcp_server.py`(stdio)는 그대로 유지 — 로컬 방식도 계속 사용 가능.

## 환경변수
| 변수 | 기본 | 설명 |
|---|---|---|
| `MCP_HTTP_HOST` | `0.0.0.0` | 바인딩 호스트 |
| `MCP_HTTP_PORT` | `8800` | 포트 |
| `MCP_HTTP_PATH` | `/mcp` | MCP 엔드포인트 |
| `MCP_AUTH_TOKEN` | (없음) | **도메인 노출 시 필수.** Bearer 검증 활성 |
| `MCP_SSL_CERTFILE` / `MCP_SSL_KEYFILE` | (없음) | 둘 다 설정 시 HTTPS |
| `MCP_ALLOWED_HOSTS` | (없음) | 콤마구분. 실도메인 지정 시 DNS rebinding 방어 |
| `MCP_JSON_RESPONSE` | `false` | true면 SSE 대신 단일 JSON |
| `MCP_GROUP` | (없음) | 특정 그룹만 노출(기존과 동일) |
| `MCP_DB_PATH` | `app/mcp_provider.db` | provider 앱과 **동일 DB** 지정 |

## 실행 (Windows 콘솔)

### 1) 의존성 (이미 설치돼 있으면 생략)
```powershell
cd C:\Users\PC-727\Documents\Claude\Projects\web-mcp-provider\app
.\venv\Scripts\Activate.ps1
pip install "mcp>=1.7" "starlette>=0.37" "uvicorn[standard]>=0.29"
```

### 2) HTTP로 기동 (내부망/프록시 뒤)
```powershell
$env:PYTHONPATH="."
$env:MCP_AUTH_TOKEN="<긴-랜덤-토큰>"
$env:MCP_GROUP="xperp"                 # 선택
python -m backend.mcp_http_server
# → http://0.0.0.0:8800/mcp 리슨
```

### 3) HTTPS로 직접 기동 (같은 도메인/인증서)
```powershell
$env:PYTHONPATH="."
$env:MCP_AUTH_TOKEN="<긴-랜덤-토큰>"
$env:MCP_SSL_CERTFILE="C:\certs\fullchain.pem"
$env:MCP_SSL_KEYFILE="C:\certs\privkey.pem"
$env:MCP_ALLOWED_HOSTS="mcp.aegisep.com"   # 실도메인
$env:MCP_HTTP_PORT="443"                    # 또는 8800 후 포워딩
python -m backend.mcp_http_server
# → https://mcp.aegisep.com/mcp
```

## 사용자 테스트 (콘솔/URL)

### A. 상태 점검 (인증 불필요)
```powershell
curl.exe http://localhost:8800/healthz
# {"status":"ok","tables":[...],"mcp_path":"/mcp"}
```

### B. 인증 동작 확인 (401 기대)
```powershell
curl.exe -i -X POST http://localhost:8800/mcp
# HTTP/1.1 401 Unauthorized
```

### C. MCP 핸드셰이크(도구 목록) — 토큰 포함
아래를 `test_http.py` 로 저장 후 실행:
```python
import asyncio
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

URL = "http://localhost:8800/mcp"          # 원격이면 https://mcp.aegisep.com/mcp
TOKEN = "<위와-동일-토큰>"

async def main():
    async with streamablehttp_client(URL, headers={"Authorization": f"Bearer {TOKEN}"}) as (r, w, _):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            print("도구 수:", len(tools.tools))
            for t in tools.tools:
                print(" -", t.name)

asyncio.run(main())
```
```powershell
python test_http.py    # 도구 목록이 출력되면 연결 성공
```

## 클라이언트 연결

### Claude Desktop (원격 URL) — `%APPDATA%\Claude\claude_desktop_config.json`
```json
{
  "mcpServers": {
    "xperp": {
      "url": "https://mcp.aegisep.com/mcp",
      "headers": { "Authorization": "Bearer <토큰>" }
    }
  }
}
```
> 원격 URL 방식은 Claude Desktop 최신 버전에서 지원됩니다. 미지원 버전은 `mcp-remote` 브리지 사용:
> `"command": "npx", "args": ["mcp-remote", "https://mcp.aegisep.com/mcp", "--header", "Authorization: Bearer <토큰>"]`

### LangGraph (MultiServerMCPClient) — `.env.local`
```ini
ENABLE_MCP_TOOLS=true
XPERP_MCP_URL=https://mcp.aegisep.com/mcp
XPERP_MCP_TRANSPORT=streamable_http
XPERP_MCP_AUTH_HEADER=Authorization: Bearer <토큰>
```

## 검증 결과 (2026-07-01, Linux 스모크)
| 항목 | 결과 |
|---|---|
| `GET /healthz` (무인증) | 200 |
| `POST /mcp` (토큰 없음/오류) | 401 |
| `initialize` + `tools/list` (토큰 O) | 도구 3개 노출 |
| HTTPS(자가서명) 기동·healthz | 200 |

## Docker Compose 배포 (다른 서버)

구성: **MCP HTTP 서버 + 관리 UI** 2개 컨테이너가 `./data` 볼륨(SQLite)을 공유.
TLS 는 **외부 리버스 프록시**가 종단하고 컨테이너는 HTTP 만 노출.

### 파일
- `app/Dockerfile` — python:3.11-slim, 공용 이미지
- `app/.dockerignore` — venv/DB/캐시 제외
- `app/docker-compose.yml` — `mcp`(9900) + `ui`(9090) 서비스
- `app/.env.example` — 환경변수 템플릿

### 배포 절차
```bash
# 대상 서버에서
cd app
cp .env.example .env          # 값 채우기(MCP_AUTH_TOKEN, MCP_ALLOWED_HOSTS 등)

# 기존 워크플로우 DB 이관(선택) — 로컬 mcp_provider.db 를 볼륨으로 복사
mkdir -p data && cp /경로/mcp_provider.db data/mcp_provider.db

docker compose --env-file .env up -d --build
docker compose ps
curl http://localhost:9900/healthz     # {"status":"ok",...}
curl http://localhost:9090/healthz     # UI
```
> DB 를 이관하지 않으면 빈 상태로 시작합니다. 이 경우 UI(:9090)에서 워크플로우를 만들고
> **MCP 노출 토글**을 켜면 `mcp` 서비스가 같은 볼륨을 보므로 즉시 반영됩니다.

### 리버스 프록시 예시 (Nginx) — SSE 버퍼링 금지 필수
```nginx
server {
    listen 443 ssl;
    server_name mcp.aegisep.com;          # MCP_ALLOWED_HOSTS 와 동일

    ssl_certificate     /etc/ssl/fullchain.pem;
    ssl_certificate_key /etc/ssl/privkey.pem;

    location /mcp {
        proxy_pass http://127.0.0.1:9900;
        proxy_http_version 1.1;
        proxy_set_header Host $host;        # DNS rebinding 체크용 Host 보존
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;                # streamable_http/SSE 스트리밍
        proxy_read_timeout 3600s;
    }
}
# 관리 UI 는 내부망/별도 도메인 권장 (예: ui.aegisep.com → 127.0.0.1:9090)
```

### 검증 결과 (2026-07-01, Linux)
| 항목 | 결과 |
|---|---|
| compose 구조(서비스·공유 DB 볼륨) | OK |
| `mcp` 이미지 실행(가상환경 import·기동) | OK |
| `ui` 서비스 `uvicorn backend.app:app` 기동·healthz | 200 |
> 도커 데몬이 없는 검증 환경이라 `docker build` 자체는 대상 서버에서 수행하세요.

### 운영 팁
- 이미지 1개를 두 서비스가 command 만 바꿔 공유 → 빌드/배포 단순.
- 컨테이너 로그: `docker compose logs -f mcp` / `ui`.
- 업데이트: `git pull && docker compose up -d --build`.
- 리버스 프록시가 Host 를 보존해야 `MCP_ALLOWED_HOSTS` 검증 통과(위 `proxy_set_header Host`).

## 운영 주의
- **토큰 필수:** `MCP_AUTH_TOKEN` 미설정 시 개방 → 워크플로우가 실제 API를 호출하므로 도메인 노출 시 반드시 설정.
- **DB 일치:** provider(UI) 앱과 동일한 SQLite를 봐야 노출 워크플로우가 일치 → `MCP_DB_PATH` 동일 지정.
- **DNS rebinding:** 도메인 노출 시 `MCP_ALLOWED_HOSTS`에 실도메인 지정 권장.
- **쓰기성 호출:** 기존 `dry_run=true` 안전장치 그대로 유지.
- 실행 감사 로그는 기존과 동일하게 `executions`에 `source="mcp"`로 기록됨.
