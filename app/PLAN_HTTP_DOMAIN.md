# MCP 서버 도메인(HTTP) 노출 플랜

## 목표
기존 stdio 기반 MCP 서버(`backend/mcp_server.py`, Claude Desktop이 로컬 프로세스로 spawn)를
**도메인에서 접속 가능한 HTTP(streamable_http) 서버**로 노출한다.

## 확정 방향 (사용자 결정)
- 노출 구조: **별도 MCP HTTP 서버 프로세스** (UI 서버 `backend.app`와 분리)
- 도메인/TLS: **앱이 직접 도메인/HTTPS** (uvicorn이 인증서 직접 로드, 0.0.0.0 바인딩)
- 인증: **Bearer 토큰(헤더) 검증** — `Authorization: Bearer <token>`

## 아키텍처
```
MCP 클라이언트(Claude Desktop / LangGraph MultiServerMCPClient)
   │  HTTPS  https://<도메인>/mcp
   ▼
uvicorn (TLS 종단, 0.0.0.0:8800)
   └ Starlette 앱  (backend/mcp_http_server.py)
        ├ BearerAuthMiddleware        ── Authorization 헤더 검증
        ├ /mcp  → StreamableHTTPSessionManager.handle_request
        │           └ 기존 low-level `server` (mcp_server.py) 재사용
        │                └ list_tools / call_tool  (툴 빌드 로직 그대로)
        └ /healthz → 상태 점검(인증 불필요)
```
- **핵심: 툴 생성/실행 로직은 재구현하지 않고 `mcp_server.py`의 `server`·`ensure_tools`를 import 하여 그대로 사용.**
  → stdio(로컬)와 HTTP(도메인) 두 진입점이 동일 로직 공유. 유지보수 이중화 없음.

## 환경변수
| 변수 | 기본값 | 설명 |
|---|---|---|
| `MCP_HTTP_HOST` | `0.0.0.0` | 바인딩 호스트 |
| `MCP_HTTP_PORT` | `8800` | 바인딩 포트 |
| `MCP_HTTP_PATH` | `/mcp` | MCP 엔드포인트 경로 |
| `MCP_AUTH_TOKEN` | (없음) | 설정 시 Bearer 검증 활성. 미설정 시 인증 없이 개방(경고 로그) |
| `MCP_SSL_CERTFILE` | (없음) | TLS 인증서(fullchain) 경로. 설정 시 HTTPS |
| `MCP_SSL_KEYFILE` | (없음) | TLS 개인키 경로 |
| `MCP_ALLOWED_HOSTS` | (없음) | 콤마구분. 설정 시 DNS rebinding 보호 활성(Host 헤더 화이트리스트) |
| `MCP_JSON_RESPONSE` | `false` | true면 SSE 대신 단일 JSON 응답 모드 |
| `MCP_GROUP` | (없음) | 기존과 동일 — 특정 그룹 워크플로우만 노출 |

## 순차 실행 단계
1. `PLAN_HTTP_DOMAIN.md` 작성 (본 문서)
2. `backend/mcp_http_server.py` 구현 (streamable_http + Bearer + TLS + healthz)
3. Linux venv 스모크 테스트: 기동 → `initialize` → `tools/list` → 인증 401 확인
4. `HANDOFF_HTTP_DOMAIN.md` 작성: Windows 실행 명령·인증서 발급·클라이언트 연결·사용자 테스트(curl/URL)
5. 사용자 콘솔/URL 테스트 제공 및 인수인계

## 보안/운영 주의
- `MCP_AUTH_TOKEN` 미설정 시 누구나 워크플로우(실 API 호출) 실행 가능 → 도메인 노출 시 **토큰 필수**.
- 쓰기성 호출은 기존 `dry_run` 안전장치 유지.
- DB(SQLite)는 provider 앱과 동일 파일을 봐야 노출 워크플로우가 일치 → 같은 `MCP_DB_PATH`.
- 도메인 노출 시 `MCP_ALLOWED_HOSTS`에 실제 도메인 지정 권장(DNS rebinding 방어).
