# MCP Provider — 그린필드 빌드 사양서 (v1)

> 새 저장소/세션에서 **처음부터** 구현하기 위한 단일 사양서.
> 기술 스택 유지: **FastAPI + Jinja2 + htmx + Drawflow + SQLite** (빌드 도구 없음, CDN/정적).
> 디자인 기준: 핸드오프 번들 "MCP Provider — 워크플로우 빌더 UI 리디자인"(클리어 라이트 + 다크 토글).
> 재사용 자산: `static/tokens.css`, `static/drawflow_node_styles.css` 는 그대로 가져다 쓸 수 있음.

---

## 0. 제품 개요
OpenAPI/Swagger 스펙(파일/URL)을 올리면 각 API 오퍼레이션을 **노드**로 만들고, 드래그앤드롭 캔버스에서 노드를 **엣지로 연결해 순차(향후 DAG+루프) 실행 워크플로우**를 구성·실행한다. 완성된 워크플로우는 **MCP 서버로 외부 MCP 클라이언트(Claude Desktop 등)에 도구로 노출**한다. 사용자엔 비개발자 포함, UI 언어 한국어.

핵심 사용자 흐름: 스펙 업로드 → 오퍼레이션을 캔버스로 드래그 → 노드 연결·파라미터 설정 → 실행/검증 → MCP 노출.

---

## 1. 프로젝트 구조
```
backend/
  app.py                 FastAPI 앱, lifespan(init_db), 라우터 등록, 정적/템플릿 마운트
  db.py                  SQLite 연결 + 멱등 스키마 + 컬럼 마이그레이션
  models.py              Pydantic 모델 (Node/Edge/WorkflowGraph/ExecutionResult 등)
  engine_bridge.py       engine 패키지 호출 래퍼(지연 import)
  mcp_server.py          MCP 서버(stdio) — 노출 워크플로우를 도구로
  routers/               specs / operations / workflows / executions
  repositories/          specs / workflows / executions (SQLite CRUD)
engine/                  순수 모듈(FastAPI 비의존)
  parser.py              OpenAPI v2/v3 → 오퍼레이션 추출
  http_client.py         httpx 래퍼(base_url+path, 인증 주입, 프로토콜 가드)
  executor.py            그래프 검증/토폴로지/순차 실행/노드별 로그
templates/               base.html, index.html, editor.html, partials/
static/                  tokens.css, style.css, drawflow_node_styles.css, canvas.js
mcp_provider.db          SQLite 단일 파일(repo 루트)
```

---

## 2. 데이터 모델 (SQLite, 멱등 DDL)
```sql
specs(id PK, name, source_type CHECK(file|url), source_ref, spec_version, raw_content, parsed_at, created_at)
operations(id PK, spec_id FK, operation_id, method, path, base_url, summary,
           params_schema, request_schema, response_schema, auth, created_at)
workflows(id PK, name, description, mcp_exposed INT DEFAULT 0,
          mcp_group TEXT, mcp_tool_name TEXT, created_at, updated_at)
nodes(id PK, workflow_id FK, node_key, operation_id FK, type, label,
      base_url TEXT, params JSON, position_x, position_y)
edges(id PK, workflow_id FK, edge_key, source_node_key, target_node_key, data_mapping JSON)
executions(id PK, workflow_id FK, status, started_at, finished_at, result)
execution_logs(id PK, execution_id FK, node_key, seq, status, input, output, error, timestamp)
```
- JSON 컬럼은 TEXT(`json.dumps`), 리포지토리가 (de)serialize.
- PK는 정수, 그래프 내부 참조는 문자열 키(node_key/edge_key).
- 신규 컬럼은 `_apply_column_migrations`(PRAGMA table_info 확인 후 ALTER)로 기존 DB에도 추가.

### 노드/엣지 와이어 모델 (계약)
```
Node   { id, type:"api_call|start|end|transform", label, operation_id?,
         base_url?, params:{path,query,header,body}, position:{x,y} }
Edge   { id, source, target, data_mapping:[{from, to}] }   # 와이어 키 "from"/"to" 고정
WorkflowGraph { workflow_id, nodes[], edges[] }
ExecutionResult { execution_id, workflow_id, status:"running|success|failed",
                  started_at, finished_at, result, logs:[NodeLog] }
NodeLog { node_key, seq, status:"success|failed|skipped", input, output, error, timestamp }
```

---

## 3. 백엔드 API
```
POST   /api/specs/upload         (multipart file)         → SpecUploadResult
POST   /api/specs/from-url       {url, name?}             → SpecUploadResult
GET    /api/operations/{id}                               → OperationOut
GET    /api/workflows                                     → [WorkflowSummary]
POST   /api/workflows            {name, description?}      → WorkflowDetail
GET    /api/workflows/{id}                                → WorkflowDetail
PUT    /api/workflows/{id}       {nodes, edges, name?, description?}  → WorkflowDetail
DELETE /api/workflows/{id}
POST   /api/workflows/{id}/run   {initial_input, auth}     → ExecutionResult
PUT    /api/workflows/{id}/expose {exposed, group?, tool_name?} → {mcp_exposed, mcp_group, mcp_tool_name}
GET    /api/executions/{id}                               → ExecutionResult
GET /              UI 셸(index.html)
GET /editor/{id}   에디터(editor.html, workflow_id 주입)
```

---

## 4. 실행 엔진 계약 (engine/)
- `parse_openapi(raw, source_hint) -> ParseResult{spec_version, base_url, operations[], warnings[]}`
  - base_url: v3 `servers[0].url`(변수 기본값 치환), v2 `scheme://host+basePath`. 없으면 None + warning.
- `run_workflow(graph, initial_input, auth, on_node_event?, *, operation_resolver, timeout) -> ExecutionResult(dict)`
  - 그래프 검증(사이클 거부) → 토폴로지 정렬 → 순차 실행. 노드 실패 시 **raise 안 함**: 해당 노드 `failed`, 이후 노드 `skipped`.
  - `start` 출력 = `initial_input`($). 엣지 `data_mapping`(`$.x`→`params.path.x`)로 상류 출력 주입.
  - `operation_resolver(operation_id:int)->dict|None` 를 백엔드가 주입(operations 조회).
- **base_url 우선순위(중요):** `node.base_url → operation.base_url → DEFAULT_BASE_URL`.
  - `DEFAULT_BASE_URL = env MCP_DEFAULT_BASE_URL or "http://localhost:8000"`.
- `http_client.call(...)`: URL에 `http(s)://` 없으면 **명확한 한글 에러로 즉시 실패**(프로토콜 가드). 인증: bearer/basic/apikey(header|query) 주입(시크릿 미영속).
- JSONPath 부분집합: `$`, 점 접근(`$.a.b`), 인덱스(`$.a[0].b`).

---

## 5. MCP 노출 (backend/mcp_server.py, stdio)
- `load_exposed_workflows()` → `mcp_exposed=1` 워크플로우 로드. `MCP_GROUP` 환경변수 있으면 `mcp_group` 일치만.
- 서버명 `MCP_SERVER_NAME or ("mcp-"+MCP_GROUP or "mcp-provider")`.
- 도구명 `build_tool_name(id, name, override=mcp_tool_name)`:
  - `mcp_tool_name` 있으면 그대로(MCP 안전문자 `[A-Za-z0-9_-]`로 정리), 없으면 `workflow_{id}_{slug}`.
  - slug는 [a-z0-9]만 → 한글 이름은 fallback. 도구명은 영문 권장, 한글 가독성은 `description`(워크플로우명).
- `build_input_schema()`: 시작 노드에 연결된 api 노드의 **미충족 필수 파라미터**(정적값/매핑으로 안 채워진 것)를 JSON Schema로.
- `apply_tool_args(graph, args, resolver)`: 도구 인자를 **deepcopy 그래프의 노드 params**(path/query/header/body)에 주입(엔진은 initial_input을 매핑으로만 주입하므로 필수). 호출 시 initial_input에도 전달.
- 도구 목록은 **서버 기동 시 1회 생성** → 노출/그룹/이름/그래프 변경 후 **MCP 클라이언트 재시작 필요**.
- Claude Desktop config 예시(그룹별 분리):
```json
{ "mcpServers": {
  "xperp": { "command": "<venv>/python", "args": ["-m","backend.mcp_server"],
             "cwd": "<repo>", "env": { "PYTHONPATH": "<repo>", "MCP_GROUP": "xperp" } } } }
```
  - `-m backend.mcp_server` 사용 시 `PYTHONPATH=<repo>` 필수(없으면 `No module named 'backend'`).

---

## 6. 디자인 시스템
폰트: **Plus Jakarta Sans**(UI) + **JetBrains Mono**(코드/경로). 라이트 기본 + `[data-theme="dark"]` 토글(localStorage `mcp-theme`, FOUC 방지 부트스트랩).

토큰은 `static/tokens.css`의 `:root`/`[data-theme="dark"]` 그대로 사용. 핵심:
- surface: `--canvas #F4F6F9`, `--surface #FFFFFF`, `--surface-2/3`, `--border/-strong`
- text: `--text-1 #1A2231 / -2 / -3`
- brand: `--brand #0E9E74`, `--brand-solid #0A7D5A`(AA 버튼 채움), `--brand-weak`
- semantic: `--success #16A34A`, `--danger #E5484D`, `--warn`, `--skip`
- 메서드 배지: `--m-get #1D6FE0`, `--m-post #0E8A5F`, `--m-put`, `--m-patch`, `--m-delete` (+ `-bg`)
- 로직 노드: `--logic-branch`(violet) / `--logic-loop`(amber) / `--logic-merge`(blue)
- shape: `--r-sm 6 / -md 8 / -lg 12 / -xl 16 / -pill 999`, `--sh-1/2/3`

간격(4px 베이스): 4·8·12·16·24·32. 타이포 스케일: 30/800(H1)·22/700·16/600·13/500·12/400·mono12.

### 컴포넌트
- 버튼: primary(`--brand-solid` 흰글씨)/secondary/ghost/danger/icon(34px). 점선 +start(브랜드)/+end(중립).
- 인풋: focus 시 1.5px brand + 3px `--focus` 링. error/disabled 상태.
- 토글(40×23), 세그먼트(`.segment/.seg-btn`, 활성=흰배경+그림자), 탭(언더라인 2px brand).
- 메서드 배지(mono 11/600), 엣지(2px `--border-strong`, 흰 포트+컬러 테두리), 토스트(좌측 상태 스트라이프).
- **노드 카드(`static/drawflow_node_styles.css`)**: Drawflow 기본 크롬 제거 후 `.wf-node` 내부 카드.
  상단 4px **상태 스트라이프 + 얇은 테두리에만 상태색**(카드 전체를 칠하지 말 것 — 빨강=실패 전용).
  `data-status`(""/success/error/skipped/running) 토글. start/end는 아이콘 타일(▶/■). 제목=요약(경로 중복 금지).

### 화면
1. **에디터 3분할**: 2단 툴바(① 제목·저장상태·테마·저장·실행 / ② +start·+end·도구이름·그룹·MCP노출) + 좌 오퍼레이션(236px) + 캔버스(도트그리드) + 우 속성/로그(296px).
2. **캔버스 도구**: 좌하단 줌(+/−/%), 상단중앙 플로팅 바(자동 정렬 + 다중선택 시 맞춤/균등 분배).
3. **실행 다이얼로그**: 아이콘 헤더 + 모드 세그먼트(폼/JSON) + 인증 세그먼트(Bearer/API Key) + 노드별 파라미터 + ▶ 실행하기.
4. **실행 로그**: 실행 헤더 + 노드 상태 카드(좌측 상태 스트라이프, input/output 펼치기). 노드 상태색은 캔버스 노드에도 반영.

---

## 7. 프론트엔드 동작 (canvas.js, Drawflow)
- 드래그: 좌측 오퍼레이션 → 캔버스 드롭 `addNode`. 노드 라벨 `"METHOD /path"` → 카드 렌더(배지+경로+요약).
- 노드 선택 → 속성 패널(정적 params·노드 base_url 편집). 엣지 선택 → data_mapping 편집(응답필드↔입력필드 클릭삽입·자동매핑).
- 실행 폼: 시작 노드에 연결된 api 노드 파라미터 자동 폼. 값은 노드 정적 params로 저장(저장 시 영속). 인증 token/api_key. JSON 직접 편집 토글.
- 줌(Drawflow zoom API), 자동 정렬(엣지 longest-path 레이어링, `pos_x/pos_y` 재작성 + `updateConnectionNodes`), 다중선택(클릭 위임+shift), 맞춤/분배.
- 테마 토글, 노드 상태색(`applyNodeStatuses` → `data-status`), 로드 시 요약 제목 갱신(`refreshNodeTitles`).

---

## 8. 제어 흐름 노드 (로드맵 — 신규 빌드 시 설계 반영)
API(데이터) 노드와 구분되는 **로직 노드**(색 아이콘 타일 + 타입 칩, 다중 출력 포트):
- 분기(violet): IF / Switch / Filter — 다중 출력 포트(참/거짓, case…/default, 통과/제외)
- 반복(amber): Loop / Batch — (루프 각 항목 / 완료), 배치 크기·병렬
- 병합(blue): Merge / Wait — 입력 2+ → 출력 1
- IF 조건 빌더: [필드][연산자][값] 행 + AND/OR + 출력 라우팅 요약.
- **실행 모델 영향(중대):** 순차 → **DAG + 루프**. 토폴로지 평가, 미선택 분기 **스킵**(회색 점선 엣지). MCP 입력스키마의 분기 입력 통합 정책 필요. ⇒ executor 재설계 필요(별도 플랜·노드 타입별 단계 테스트 권장).

---

## 9. 빌드 순서 (권장)
1. 스캐폴드: FastAPI 앱 + db.py(스키마/마이그레이션) + 모델 + 정적/템플릿 마운트.
2. engine: parser → http_client(base_url 우선순위·가드) → executor(순차) + 단위 테스트.
3. specs/operations/workflows/executions 라우터 + 리포지토리.
4. 프론트: tokens.css + drawflow_node_styles.css + style.css + base/editor 템플릿 + canvas.js(캔버스/노드/속성/엣지매핑/실행폼).
5. 캔버스 도구(줌/자동정렬/다중선택/맞춤·분배), 테마 토글.
6. MCP: mcp_server(load/resolver/build_input_schema/apply_tool_args) + expose 엔드포인트 + 에디터 UI(노출/그룹/도구이름). config 연동.
7. (별도 플랜) 제어 흐름 노드 + 엔진 DAG/루프 — 노드 타입별로 하나씩 테스트하며 적용.

각 단계는 **플랜 구성 → 순차 실행 → 핸드오프** 원칙, 단계마다 로컬 브라우저/엔드포인트로 검증.

---

## 10. 알려진 이슈 / 주의
- **샌드박스 마운트 한계:** 대용량 파일(canvas.js)·바이너리(.db) 읽기가 truncate/손상으로 나올 수 있고, `.git` 쓰기·삭제가 제한될 수 있음 → **git 커밋/푸시·DB 편집은 로컬에서** 수행.
- MCP 도구 목록은 서버 기동 시 고정 → 변경 후 클라이언트 재시작.
- base_url 기본값 상수가 executor·canvas.js 2곳 → 변경 시 동기화(또는 env 우선).
- 더미 API 서버(:8000) ↔ provider 앱(:9000) 포트 구분.
- 도구명 slug는 영문/숫자만 유효(한글 이름→fallback). 한글은 description으로.

## 11. 참고 자산
- 디자인 번들: `디자인 시스템.dc.html`(메인 레퍼런스), `스타일 방향 무드보드.dc.html`, README(토큰/사양).
- 기존 핸드오프: `_workspace/06_base_url_handoff.md`(base_url·MCP), `07_redesign_handoff.md`(UI 리디자인).
- 재사용 CSS: `static/tokens.css`, `static/drawflow_node_styles.css`.
