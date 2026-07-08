# HANDOFF — tools/list 에 출력 스키마(outputSchema) 노출 + structuredContent 반환

작성일: 2026-07-08 · 대상: web-mcp-provider (app) · 관련: [[HANDOFF_INPUT_MODE]]

## 0. 목표

`tools/list` 응답에 각 도구의 **반환값 구조(outputSchema)** 를 함께 노출해,
에이전트(LLM/LangGraph)가 입력뿐 아니라 **출력까지 보고 어떤 툴을 호출할지 판단**할 수 있게 한다.

## 1. 배경 / 문제

기존 `list_tools()` 는 `name / description / inputSchema` 만 내보냈다. 출력 스키마가 없어
에이전트는 각 툴이 무엇을 돌려주는지 알 수 없었다. 또한 응답 스키마는 오퍼레이션마다
저장돼 있으나 `{"$ref": "#/components/schemas/ImpoDetailResp"}` 처럼 **미해소 참조**였다.

## 2. 해결

1. **$ref 인라인 해소** — 스펙 원문(`specs.raw_content`)의 `components/schemas` 를 이용해
   종단 오퍼레이션의 `response_schema` 를 재귀적으로 인라인(순환·깊이 방어).
2. **outputSchema 부착** — `types.Tool(outputSchema=...)` 로 노출(SDK 필드 존재 시에만).
3. **structuredContent 반환** — `call_tool` 이 텍스트(기존과 동일)와 함께 구조화 응답을 반환.

### 검증 안전(중요)

mcp 1.28.0 의 `@server.call_tool()` 은 **outputSchema 가 선언되면 모든 응답의
structuredContent 를 강제 검증**한다(불일치·누락 시 에러). 성공(응답 본문)·`dry_run`·오류
페이로드는 형태가 서로 다르므로, outputSchema 는 **서술 정보(properties/type/description)는
유지하되 검증을 막지 않도록 완화**한다:

- 모든 오브젝트에서 `required` 제거, `additionalProperties: false → true`.
- 최상위 properties 에서 예약 응답 키(`dry_run, status, planned_actions, preview, note, node, error`)
  제거 → dry_run·오류 페이로드 키와의 타입 충돌 원천 차단.
- 비오브젝트 응답은 `{ "result": <schema> }` 로 래핑(outputSchema 는 object 유지).

→ 기존 성공 응답 계약(raw `final`)·텍스트 content 는 **그대로 유지**(하위호환), structuredContent 만 추가.

## 3. 변경 파일

- `backend/mcp_server.py`
  - `_spec_schemas(spec_id)`: 스펙 `components/schemas` 로드·캐시(`get_spec_raw`).
  - `_resolve_refs()`: `$ref` 재귀 인라인(순환=참조만 남김, depth>12 방어).
  - `_relax_schema()`: `required` 제거 + `additionalProperties` 개방(서술 정보 보존).
  - `_terminal_operation_id(graph)`: `end` 노드로부터 역방향 최근접 api_call 오퍼레이션.
  - `build_output_schema(graph)`: 위 조합 → 검증안전 outputSchema(없으면 None).
  - `build_tools()`: 도구에 `output_schema` 저장, 스펙 캐시 초기화.
  - `list_tools()`: `outputSchema` 부착(SDK 필드 있을 때만, 구버전 호환).
  - `call_tool()`: `(content, structured)` 튜플 반환. structured 는 dict, 아니면 `{result:...}`.
- HTTP 진입점 `backend/mcp_http_server.py` 는 `mcp_server` 의 `server`·핸들러를 그대로
  재사용하므로 **자동 반영**(별도 수정 없음).

## 4. 입력 파라미터 노출(고정모드 툴)

`get_resident_uesr` 등 `dry_run` 만 보이던 툴은 노드에 정적값(`aptcd/dong/ho`)이 박혀
있어서 입력에서 숨겨진 것(설계상 고정모드). 기존 범용 스크립트로 정적값만 지우면 자동 노출된다.

```powershell
# app 디렉터리에서. 먼저 미리보기(dry-run) → 실제 적용
venv\Scripts\python scripts\expose_workflow_params.py --wf <워크플로우id> --dry-run
venv\Scripts\python scripts\expose_workflow_params.py --wf <워크플로우id>
```

- 이 스크립트는 자동 DB 백업 + `workflows.updated_at` 갱신(→ `tools/list_changed` 알림).
- 대상 워크플로우 id 는 `/`(목록) 또는 에디터에서 확인. `get_resident_uesr_car` 도 동일.
- 적용 후 aptcd(required)·dong·ho 가 평면 입력으로 노출된다([[HANDOFF_INPUT_MODE]] 참조).

## 5. 테스트 (콘솔 / URL — 사용자 진행)

### 5-1. MCP Inspector (권장)

```powershell
cd <repo>\app
$env:PYTHONPATH="."; $env:MCP_GROUP="xperp"
npx @modelcontextprotocol/inspector .\venv\Scripts\python.exe -m backend.mcp_server
```

- 콘솔에 출력되는 URL(기본 UI `http://localhost:6274`) 접속 → **Tools** 탭.
- 각 도구에 **Input Schema** 와 **Output Schema** 가 함께 보이는지 확인.
- 도구 실행 시 응답 하단 **structuredContent** 채워지는지 확인.

### 5-2. HTTP 진입점(JSON-RPC)

```bash
# 서버: PYTHONPATH=. python -m backend.mcp_http_server  (기본 :8800/mcp)
curl -s -X POST http://localhost:8800/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -H 'Authorization: Bearer <MCP_AUTH_TOKEN>' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'
```

기대: 각 tool 객체에 `inputSchema` + `outputSchema` 동시 존재.
`get_apt_code` → outputSchema 에 `query/count/items[aptcd,name,address]/...`(AptCodeResp 인라인).

### 5-3. 오프라인 검증(이 세션에서 완료)

- wf6(ImpoDetailResp)·wf7(AptCodeResp): outputSchema 정상 생성(중첩 `$ref` 인라인 확인).
- 성공 / dry_run / 오류 세 페이로드 모두 outputSchema 검증 **통과**.
- wf8(occp_unit): 응답 스키마 `{}` → outputSchema None(안전). 런타임 스펙에 응답 모델이
  있으면 자동 채워짐.

## 6. 주의 / 후속

- **마운트 쓰기 제약**: 이 세션의 리눅스 샌드박스는 마운트 위 SQLite commit 시 `disk I/O error`
  발생(알려진 캐시 truncate 이슈) → **DB 변경은 사용자 개발환경에서 스크립트로 진행**.
  DB 무결성은 확인 완료(`integrity: ok`), 데이터 손실 없음. 백업: `mcp_provider.db.bak_20260708_160344`.
- 코드(outputSchema) 변경은 DB 무관·환경 독립. 런타임(18800/spec 6)에도 동일 적용.
- 응답 모델이 없는 오퍼레이션은 outputSchema 미노출(강제 검증 회피). 필요 시 OpenAPI 스펙에
  응답 스키마를 채우면 자동 노출된다.
