# XpERP MCP 서버 연동 가이드 (챗봇 에이전트용)

/ MCP 서버가 **로컬 stdio → 원격 HTTP(도메인)** 로 전환되었습니다.
챗봇(LangGraph MultiServerMCPClient)은 프로세스를 직접 띄우지 않고 **URL로 접속**합니다.

## 1. 접속 정보

| 항목 | 값 |
|---|---|
| Endpoint URL | `https://panthip.ddns.net:29900/mcp` |
| Transport | `streamable_http` |
| 인증 | `Authorization: Bearer <MCP_AUTH_TOKEN>` (헤더) |
| 프로토콜 | MCP `2025-06-18` (streamable HTTP, SSE 응답) |

> 토큰은 별도 보안 채널로 전달합니다(문서/저장소에 평문 커밋 금지).
> TLS 는 리버스 프록시가 종단하며, 컨테이너는 내부 HTTP 로 동작합니다.

## 2. 챗봇 .env 설정

기존 stdio 설정을 아래로 교체합니다.

```dotenv
ENABLE_MCP_TOOLS=true

# 원격 HTTP 전환
XPERP_MCP_TRANSPORT=streamable_http
XPERP_MCP_URL=https://panthip.ddns.net:29900/mcp
XPERP_MCP_AUTH_HEADER=Authorization: Bearer <MCP_AUTH_TOKEN>

# stdio 전용 키는 불필요 → 삭제(있어도 streamable_http 면 무시)
# XPERP_MCP_COMMAND / XPERP_MCP_ARGS / XPERP_MCP_ENV
ENABLE_MENU_MCP=false
```

## 3. MultiServerMCPClient 구성 (langchain-mcp-adapters)

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

client = MultiServerMCPClient({
    "xperp": {
        "transport": "streamable_http",
        "url": "https://panthip.ddns.net:29900/mcp",
        "headers": {"Authorization": "Bearer <MCP_AUTH_TOKEN>"},
    }
})
tools = await client.get_tools()   # 아래 3개 도구 로딩
```

## 4. 노출 도구 (현재 3개)

| 도구명 | 설명 | 필수 인자 | 선택 인자 |
|---|---|---|---|
| `get_resident_uesr` | 입주자·세대 단건/조건 조회 | (없음) | `dry_run` |
| `get_apt_code` | 단지코드 조회 | `name`(아파트명, 부분일치) | `dry_run` |
| `get_impo_bill_detail_yearmm` | 세대별 관리비 부과 조회 | `aptcd`(단지코드 6자리), `yearmon`(YYYYMM) | `dong`(동), `ho`(호), `dry_run` |

- 인자 이름은 **평면(자연어 친화)** 으로 노출됩니다(`aptcd`, `yearmon`, `dong`, `ho`) → 슈퍼바이저가 그대로 채우면 됩니다.
- **`dry_run`**: 모든 도구에 공통. `true` 면 변경성 호출(POST/PUT/DELETE/PATCH)을 실행하지 않고 실행 계획(`planned_actions`)만 반환. 쓰기성 작업은 먼저 `dry_run=true` 로 확인 후 사용자 승인 시 재호출 권장.
- 도구 목록은 서버가 노출 워크플로우 변경을 감지해 갱신합니다. 클라이언트는 재연결 시 최신 목록을 받습니다.

## 5. 연결 테스트 (검증된 curl)

MCP 는 초기화 핸드셰이크가 필요하고, **`Accept` 에 `application/json` 과 `text/event-stream` 둘 다** 있어야 합니다.

```bash
curl --location 'https://panthip.ddns.net:29900/mcp' \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --header 'Authorization: Bearer <MCP_AUTH_TOKEN>' \
  --data '{
    "jsonrpc":"2.0","id":1,"method":"initialize",
    "params":{"protocolVersion":"2025-06-18","capabilities":{},
              "clientInfo":{"name":"postman","version":"1.0"}}
  }'
```

정상 응답(요약):
```
HTTP/1.1 200 OK
content-type: text/event-stream
mcp-session-id: <세션ID>

event: message
data: {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18",
       "serverInfo":{"name":"mcp-provider","version":"1.28.1"}, ...}}
```

이어서 도구 목록 확인(위 응답의 `mcp-session-id` 를 헤더로 전달):
```bash
curl --location 'https://panthip.ddns.net:29900/mcp' \
  --header 'Content-Type: application/json' \
  --header 'Accept: application/json, text/event-stream' \
  --header 'Authorization: Bearer <MCP_AUTH_TOKEN>' \
  --header 'mcp-session-id: <세션ID>' \
  --data '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
```

## 6. 트러블슈팅 (응답 코드별)

| 코드 | 원인 | 조치 |
|---|---|---|
| `401` | 토큰 없음/불일치 | `Authorization: Bearer <토큰>` 정확히 전달 |
| `421` | Host 헤더가 서버 허용목록(`MCP_ALLOWED_HOSTS`)과 불일치 | 접속 도메인을 서버 허용목록에 추가(운영 담당). 프록시가 `Host` 보존 필요 |
| `406` | `Accept` 헤더에 `text/event-stream` 누락 | `Accept: application/json, text/event-stream` 둘 다 지정 |
| `307` | `/mcp` → `/mcp/` 리다이렉트 | 정상. 클라이언트가 자동 추적(대부분 지원) |
| `400` (`Missing session ID`) | initialize 없이 호출 | 먼저 `initialize` → 받은 `mcp-session-id` 로 후속 호출 |

## 7. 운영 메모

- 서버는 stdio 진입점(`backend.mcp_server`)과 동일 로직을 공유하는 HTTP 진입점(`backend.mcp_http_server`)으로 동작 → 도구 스키마·동작 동일.
- 실행 감사 로그는 provider DB `executions` 에 `source="mcp"` 로 기록됨.
- 그룹 분리가 필요하면(예: common / resident) 서버 측에서 그룹별 엔드포인트(`/mcp/<group>`)를 추가 배포할 수 있음 → 필요 시 인프라 담당에게 요청.

---
문의: 인프라/서버 담당 (MCP Provider 운영). 토큰 재발급·도메인/허용목록 변경은 서버 측 `.env` 반영 후 재기동 필요.
