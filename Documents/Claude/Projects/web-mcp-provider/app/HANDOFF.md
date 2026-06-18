# 핸드오프 — MCP Provider 그린필드 빌드

> 작성: 2026-06-17 · 위치: `web-mcp-provider/app/`
> 기준 문서: `../08_greenfield_build_spec.md` (사양서 v1), `_design_ref/BUILD_GUIDELINES.md` (디자인 합격 기준)

## 이번 주 (이번 세션 완료분)
- 콘솔 접속 및 `app/` 프로젝트 구조 생성.
- 재사용 자산 배치: `static/tokens.css`, `static/drawflow_node_styles.css`, 디자인 레퍼런스(`_design_ref/`).
- 의존성 설치 확인: FastAPI 0.137 / Pydantic 2.13 / httpx 0.28 / Jinja2 / PyYAML / pytest (Python 3.10).
- 빌드 플랜 작성(`PLAN.md`).
- 1단계 스캐폴드(app.py / db.py / models.py / 정적·템플릿 마운트).
- 2단계 엔진(parser / http_client / executor) + pytest 단위 테스트.

## 3단계 완료분 (2026-06-17 추가)
- 리포지토리: `repositories/specs.py`(스펙+오퍼레이션 저장, operation_resolver), `workflows.py`(CRUD+그래프 (de)serialize+expose), `executions.py`(실행+로그 저장/조회).
- 라우터: `routers/specs.py`(upload/from-url/목록/오퍼레이션), `operations.py`, `workflows.py`(CRUD+run+expose), `executions.py`. 사양서 §3 엔드포인트 전부.
- 더미 API 서버 `tools/dummy_api.py`(:8000) + 테스트 가이드 `TESTING.md`.
- 검증: pytest **20 passed**(엔진18+API통합2), 라이브 e2e(스펙등록→그래프저장→실행) `/users/1` 호출 성공.
- 조치: 샌드박스 SOCKS 프록시로 인한 httpx 실패 → `http_client`/`from-url` 이 시스템 프록시 무시(기본). `MCP_HTTP_TRUST_ENV=1` 로 복구 가능.

## 4단계 완료분 (2026-06-17 추가)
- 프론트엔드: `templates/editor.html`(3분할 셸: 툴바1 52px/툴바2 46px/좌236·캔버스·우296), `static/style.css`(컴포넌트·도트그리드·다이얼로그·로그카드), `static/canvas.js`(Drawflow 코어 450행).
- 기능: 오퍼레이션 로드·드래그앤드롭 addNode, 노드 카드 렌더(배지+경로+요약, 상태 스트라이프), 워크플로우 로드/저장(PUT), 속성 패널(base_url·params), 엣지 데이터 매핑 편집, 실행 다이얼로그(폼/JSON·인증 Bearer/APIKey), 실행 로그(노드 상태색 반영), 줌·테마 토글·MCP 노출.
- Drawflow는 CDN(0.0.59) 로드. 재사용 CSS(tokens/drawflow_node_styles) + style.css 조합.
- 검증: pytest 20 passed 유지, `/editor/{id}` 렌더 요소 누락 없음, canvas.js `node --check` 통과, style.css 깨진 var() 없음(토큰명 `--brand-fill` 사용).
- 미구현(다음): 5단계 캔버스 도구(자동정렬/다중선택/맞춤·분배), 제어흐름 노드(7단계). 노드 제목은 현재 요약 텍스트, BUILD_GUIDELINES 픽셀 미세조정은 브라우저 비교 후 보정 권장.

## 4R 완료분 — 디자인팀 예제 기준 재구성 (2026-06-17)
- 디자인팀이 제공한 `워크플로우 빌더 예제.html`(완성형 레퍼런스)을 기준으로 프론트 전면 재구성.
- `static/style.css`: 예제 컴포넌트 CSS를 추출 적용(클래스 체계 `.tb1/.tb2/.wf-node .stripe/.nbody/.nhead/.badge/.path/.title/.nstatus` 등). 토큰은 tokens.css 사용. `drawflow_node_styles.css`는 editor.html 에서 제거(예제 CSS가 대체).
- `templates/editor.html`: 예제 마크업(2단 툴바·3분할·정렬바·줌·실행 다이얼로그·토스트) + Jinja workflow_id + 백엔드 연동 ID.
- `static/canvas.js`(512행, 전역 함수 스코프): 예제 노드 HTML/드롭/속성/실행/정렬·분배/자동정렬/토스트/테마 채택 + 백엔드 실연동(오퍼레이션 API 로드, params 시드(스키마 default/examples), 저장 PUT, 실행 run + 노드 상태/엣지색/로그, 노출 expose). 5단계 정렬도구도 이 단계에서 포함됨.
- 엣지 화살표 마커(`#wf-arrow`) + 실행 성공 초록/스킵 점선.
- 검증: style.css var() 미정의 0, editor.html 참조 정상, canvas.js 정본 무결성 Read 확인(마운트 스테일로 node --check 는 불가).

## 다음 주 계획 (다음 작업자 인수)
- 시안 1:1 픽셀 미세 점검(BUILD_GUIDELINES 체크리스트) — 브라우저 비교.
- 다중선택(현재 Drawflow 단일선택; 정렬은 전체 노드 대상) 정식 구현.
- 6단계: MCP 노출 서버(`backend/mcp_server.py`) + Claude Desktop config.
- 6단계: MCP 노출(`backend/mcp_server.py`) + expose 엔드포인트 + 에디터 UI + Claude Desktop config.
- (별도 플랜) 7단계: 제어 흐름 노드 + 엔진 DAG/루프 재설계.

## 환경 / 실행 방법
```bash
cd app
# 의존성: fastapi uvicorn[standard] jinja2 httpx pydantic pyyaml python-multipart pytest
PYTHONPATH=. python3 -m pytest tests -q          # 엔진 단위 테스트
PYTHONPATH=. uvicorn backend.app:app --port 9000 # 앱 기동 (provider=:9000)
```
- 더미 API 서버는 :8000, provider 앱은 :9000 으로 포트 구분(사양서 §10).
- `DEFAULT_BASE_URL = env MCP_DEFAULT_BASE_URL or "http://localhost:8000"`.

## 재사용 자산 / 참고
- `static/tokens.css`, `static/drawflow_node_styles.css` — 그대로 사용(하드코딩 hex 금지, `var(--*)`만).
- `_design_ref/디자인 시스템 (standalone).html` — 메인 시안. 화면 구현 시 옆에 띄우고 1:1 비교.
- `_design_ref/BUILD_GUIDELINES.md` — 화면별 체크 가능한 합격 기준(가장 중요: 노드 카드 §4).

## 이슈 / 리스크
- **Jinja2 ≥ 3.1 필수:** 시스템 기본 3.0.3 에서는 Starlette 가 깨짐. `requirements.txt` 의 `jinja2>=3.1` 로 고정.
- **TemplateResponse 우회:** 설치된 Starlette 빌드의 `TemplateResponse` 가 컨텍스트 dict 를 템플릿 이름 자리로 전달하는 버그 → `backend/app.py` 의 `render()` 헬퍼로 `env.get_template(name).render(...)` 직접 호출.
- **샌드박스 마운트 한계:** 대용량 `canvas.js`·바이너리 `.db` 읽기가 truncate되거나, 편집 직후 bash 마운트가 구버전을 캐싱할 수 있음 → 런타임 검증은 `/tmp` 복사본에서, git 커밋/푸시·DB 편집은 로컬에서.
- MCP 도구 목록은 서버 기동 시 고정 → 노출/그룹/이름/그래프 변경 후 MCP 클라이언트 재시작 필요.
- `DEFAULT_BASE_URL` 상수가 executor·canvas.js 2곳에 존재 → 변경 시 동기화(env 우선 권장).
- 도구명 slug는 영문/숫자만 유효(한글 이름 → fallback). 한글 가독성은 `description`으로.

## 조치 / 검증 기록 (2026-06-17)
- pytest: **18 passed** (parser v2/v3·base_url·서버변수, http_client 우선순위·프로토콜가드·인증, executor JSONPath·사이클거부·순차실행·실패스킵·무raise).
- 앱 기동(TestClient): `/healthz` 200(테이블 7개), `/` 200, `/editor/{id}` 200(workflow_id 주입 확인), `/static/*` 200.
- DB 초기화: specs·operations·workflows·nodes·edges·executions·execution_logs 7개 테이블 멱등 생성 확인.
- 조치: Jinja2 3.0.3→3.1.6 업그레이드, TemplateResponse 버그를 `render()` 헬퍼로 우회.

## 6단계 완료분 — MCP 노출 + Claude Desktop (2026-06-17)
- `backend/mcp_server.py`(stdio, 163줄): `load_exposed_workflows`(MCP_GROUP 필터), `build_tool_name`(override 정리/slug fallback), `build_input_schema`(시작 연결 api 노드의 미충족 필수 파라미터 → JSON Schema, 키 `node.loc.param`), `apply_tool_args`(deepcopy 그래프에 주입), `list_tools`/`call_tool` 핸들러 + 엔진 실행.
- 검증(in-process): 노출 워크플로우→도구 `get_impo_detail` 생성, 입력스키마=미충족 필수(aptcd·yearmon required), call_tool 시 인자가 n1.query 로 주입되어 엔진 실행. (status=failed는 샌드박스에 더미API 없어서; 실제 :8000 있으면 success)
- `MCP_SETUP.md`: 노출 절차·`pip install mcp`·Claude Desktop config(JSON)·DB 공유/재시작 주의.
- 의존성: `mcp` 패키지 필요(venv 에 설치). 도구 목록은 서버 기동 시 1회 → 변경 후 클라이언트 재시작.

## 남은 로드맵
- 7단계: 제어 흐름 노드(IF/Loop/Switch/Batch/Merge/Filter) + executor DAG/루프 재설계(별도 플랜).
- 부가: 실행 이력 드롭다운(GET /api/executions 목록), 정식 다중선택, 시안 픽셀 미세조정.

## DRAWFLOW_GOTCHAS 정합 점검 (2026-06-17)
디자인팀 `DRAWFLOW_GOTCHAS.md` 5개 함정 전부 반영 확인:
1. $ref 크래시 → `slimOp`(스키마 미주입, id/method/path/summary 만) ✓
2. 화살표 → 단일 `#df-arrow` 마커 + `fill:context-stroke`(선 색 자동 추종, hover 초록) ✓
3. 노드 이동 → `moveNode` rAF 트윈 + **매 프레임 updateConnectionNodes**(CSS 트랜지션 제거) ✓
4. 드롭 → `dragover preventDefault` + 좌표보정 `(clientX-rect.left-canvas_x)/zoom` + draggable, 클릭 추가 폴백(htmx 미사용) ✓
5. 상태색 → 스트라이프+테두리만·빨강=실패·Drawflow 크롬 제거·제목=요약/경로 1회 ✓
BUILD_GUIDELINES §8 자가점검 1~4 프로그램 검증 통과(깨진 var() 0, 노드 전체 배경채움 0). §8.5(standalone 1:1)는 브라우저 육안 비교 권장.

## 메인 화면 + 설명/다중선택 추가 (2026-06-17)
- 메인(`templates/index.html`): 워크플로우 카드 목록(이름·MCP그룹·노출·메서드 배지·노드 수·수정시각), 생성(설명 입력 포함)·복제·삭제, 스펙 파일/URL 업로드, 검색·테마. `GET /api/workflows`에 `node_count·methods` 추가(모델·리포지토리).
- 에디터: 이름 옆 ✎ → **레이어 모달**(metaOverlay)로 이름·설명 편집, 저장 시 `description` PUT 반영(MCP 도구 설명으로 사용).
- 다중 선택: Shift+클릭으로 노드 선택 → 선택 노드 기준 정렬/균등분배(선택 0이면 전체), 하단 선택 컨텍스트 바.
- moveNode rAF 트윈(매 프레임 updateConnectionNodes), 화살표 df-arrow(context-stroke). DRAWFLOW_GOTCHAS 5개 모두 반영, BUILD_GUIDELINES §8 1~4 통과. 회귀 pytest 20 passed.

## 7단계 (1차) — 조건 분기(IF) 최소 구현 (2026-06-17)
- 범위: condition 노드만. Loop/Switch/Merge UI·엔진 재설계는 후속(PLAN_STAGE7.md "비범위").
- 모델/DB: `NodeType += condition`, `Edge.label`(true/false), `edges.label` 컬럼 + 마이그레이션.
- 엔진(executor): `condition` 처리 — 첫 상류 출력 기준 `eval_condition(left/op/right)` 평가 → true/false. 미선택 분기의 **배타적 하류만 skipped**(선택 분기에서 도달 가능하면 살림 → Merge 재합류 지원). 조건 평가 실패 시 노드 failed + 전체 하류 스킵. 연산자: == != > < >= <= contains exists truthy falsy(숫자/문자 혼합 비교 관용).
- 프론트(canvas.js): 로직 팔레트 "분기(IF)" 클릭/드래그로 조건 노드(입력1·출력2 true/false) 추가, 우측 속성 패널서 left/op/right 편집, exportGraph 타입·엣지 라벨(출력 포트→라벨), loadWorkflow 포트 복원. style.css 조건 노드/포트/select 스타일.
- 검증: pytest **24 passed**(신규 4: eval_condition·true·false·merge재합류). API e2e: PUT 라벨 라운드트립, flag=yes→a success/b skipped, flag=no→반대. 에디터 렌더/canvas.js 서빙 OK. node --check 통과.
- 함정 재발: Edit 툴이 backend 4파일(models/db/workflows/executor) 디스크 truncate → 전부 bash `cat>` 정본 재작성으로 복구(기존 메모리 web-mcp-provider-env 참고).
- 테스트(사용자): 콘솔 `MCP_DB_PATH=... PYTHONPATH=. pytest tests -q`. URL `/editor/{id}` → 좌측 "로직" 탭 → 분기(IF) 추가 → start→IF→(true)…/(false)… 연결 → 우측서 조건 설정 → 저장 → 실행, 로그서 스킵 경로 확인.

## ⚠️ 중요 함정 — editor.html 인라인 (2026-06-17)
- `templates/editor.html`은 `{% raw %}...{% endraw %}` 사이에 **canvas.js 전체와 style.css 전체를 인라인**한다.
  실제로 서빙되는 코드는 `static/canvas.js`/`static/style.css`가 아니라 **editor.html 안의 복사본**이다.
- 즉 에디터 화면 동작/스타일을 바꾸려면 **반드시 editor.html을 수정**해야 한다. static/ 만 고치면 화면에 반영되지 않는다(7단계 IF 1차 때 이 함정으로 화면 무반영 발생).
- 권장: 동일 변경을 editor.html 인라인본과 static/ 양쪽에 적용해 동기 유지(또는 향후 editor.html을 외부 `<script src>`/`<link>`로 전환).
- 7단계 IF 변경은 editor.html 인라인본에도 반영 완료(buildLogicPalette·addConditionNode·exportGraph 라벨·loadWorkflow 포트·showProps 조건편집·조건 CSS). 인라인 JS node --check 통과, `/editor/1` 렌더에 신규 문구/핸들러 포함 확인.

## 리턴값 미리보기 — 속성 패널 (2026-06-17)
- 요구: API 노드 선택 시 그 노드가 리턴하는 값을 미리 보고 싶다(조건/매핑 작성용).
- 엔진: `engine/schema_fields.py` — 스펙 원문 기준 `$ref`(components/definitions) 해소 + allOf 병합 + 중첩 object/array 평탄화(깊이/사이클 가드) → `fields:[{path,type,required}]`, 타입 기반 `example` 생성.
- 백엔드: `specs_repo.get_spec_raw(spec_id)`, `GET /api/operations/{id}/response-fields` → `{fields, example, ref, note}`.
- 프론트(editor.html 인라인 + static/canvas.js): showProps API 노드에 "리턴값 미리보기" 섹션 — JSONPath 필드 목록(클릭 시 클립보드 복사) + 예시 응답 JSON. CSS `.ret-*`.
- 검증: pytest **30 passed**(신규 schema 6). e2e: 스펙 업로드→`$ref` 해소 필드(`$.items[0].dong` 등)·예시 확인, /editor 렌더에 `loadReturnPreview`/`retBox` 포함. 인라인 JS·canvas.js node --check 통과.
- 한계: response_schema 가 $ref/객체일 때 유효. 원시타입/미정의면 note 안내(향후 '샘플 호출' 버튼으로 실제 응답 확인 옵션 가능).

## 7단계(2차) — Switch / Merge / Filter (2026-06-17)
- 범위: Switch·Merge·Filter 추가(Loop·Batch 제외). 스위치 케이스 **최대 10**.
- 모델: NodeType += switch/merge/filter. (edges.label 재사용: switch는 케이스값/"__default__")
- 엔진(executor):
  - switch: subject의 left 값을 케이스와 비교, 일치 엣지 채택·없으면 __default__, 미채택 분기 배타적 하류 skip. 출력=통과.
  - merge: 상류 출력 {노드id:출력} 합류(스킵된 분기 제외). 항상 success.
  - filter: 조건 참→통과, 거짓→success+전체 하류 skip(걸러짐), 평가오류→failed+skip.
- 프론트(editor.html 인라인 + static/canvas.js): 로직 팔레트(IF/스위치/병합/필터, 루프 제외), 노드 빌더, 스위치 케이스 편집(추가/삭제·최대10·포트 동기 addNodeOutput/removeNodeOutput·포트 라벨), 필터 조건 편집, 병합 안내, exportGraph 타입/스위치 라벨, loadWorkflow 노드/포트 복원. 토큰 --logic-switch/--logic-filter, 카드/포트/케이스 CSS.
- 검증: pytest **34 passed**(신규 switch/filter/merge 4). e2e: 스위치 PUT 라벨 라운드트립, status=pending→P만 실행, status=xxx→default(D) 실행. /editor 렌더에 팔레트·빌더 포함. 인라인 JS·canvas.js node --check 통과.
- 한계: 스위치 포트 라벨은 DOM(span.port-label)로 표시(케이스 텍스트 동적). MCP 입력 스키마의 switch/merge 경로 인지는 후속.

## 로직 노드 실행 결과 로그 표시 (2026-06-17)
- 요구: 로직 노드 실행 로그에 평가 결과를 함께 표시(예: $.success == true → false).
- 엔진: 로그 output enrich — condition `{branch,expr,value,result}`, switch `{switch,matched,expr}`, filter `{passed,filtered,expr,value}`. `_cond_expr()` 식 문자열 생성.
- 프론트(editor.html 인라인 + canvas.js): buildLog 가 로직 노드 로그에 "결과" 줄 렌더(식 → true/false·매칭케이스·통과/차단, 색상 칩). CSS `.lc-result/.lr-expr/.lr-val`.
- 검증: pytest **34 passed**(condition 테스트 단언 갱신). e2e: `$.success == true` → output {branch:false, expr:"$.success == true", value:"false", result:false}, 로그 카드에 결과 줄 포함.

## 결과 언래핑 + final + 로그 복사 (2026-06-17)
- 문제: end(종료) 노드가 상류 출력을 {노드ID: 출력}로 감싸 `{"3": {...}}`로 전달됨.
- 엔진: end 단일 상류→그대로 통과(래핑 제거), 다중→리스트. 실행 결과에 `final`(end 출력 우선, 없으면 마지막 성공 노드 출력) 추가. ExecutionResult.final 모델 필드.
- MCP: call_tool 이 성공 시 `final`(깔끔한 값)만 반환, 실패 시 {status,node,error} 요약 반환(기존엔 전체 result+logs 덤프).
- 프론트: 실행 로그 헤더에 "⧉ 복사" 버튼({status,final,logs} JSON 복사, 노드ID map 제외) + 로그 상단 "최종 결과" 블록(res.final).
- 검증: pytest **36 passed**(end 통과/리스트 2 신규). e2e: end OUTPUT·final 모두 `{"data":{...}}`로 언래핑, /editor 에 logCopy·최종 결과 포함.

## bool 비교 수정 + 로그 노드명 (2026-06-17)
- 버그: 조건 `$.success == true` 가 false. 원인 — JSON 불리언 true vs 우변 문자열 "true" 비교에서 `str(True)`="True"≠"true". 
- 엔진: `_coerce_eq` 에 bool↔"true"/"false"(/1/0/yes/no) 관용 비교(`_as_bool`) 추가. == / != 에 반영.
- 프론트(editor.html 인라인 + canvas.js): buildLog 가 노드명을 표시 — api=오퍼레이션 요약, 로직/터미널=한글 명(조건 분기/스위치/병합/필터/시작/종료/변환) + 타입 배지(IF/SW/MG/FT 또는 메서드).
- 검증: pytest **37 passed**(bool 비교 1 신규). e2e: success:true → result true, a 실행/b 스킵. 로그 노드명/배지 렌더 확인.

## 조건 우변 타입 지정 (rtype) (2026-06-17)
- condition/filter 우변에 `rtype` 추가: auto(기본·기존 관용)/string/number/boolean/null.
- 엔진: `_typed_eq(lhs, rhs, rtype)` — string=문자열 동등, number=float 비교, boolean=_as_bool 동등, null=lhs is None, auto=_coerce_eq. >,<,>=,<= 도 rtype=string 이면 문자열 정렬, 그 외 숫자. `_cond_expr` 에 ` :type` 표기.
- 프론트(editor.html 인라인+canvas.js): 조건/필터 패널에 "우변 타입" select(rtypeOptions), apply 시 params.condition.rtype 저장(JSON 라운드트립).
- 검증: pytest **38 passed**(rtype 1 신규). /editor 에 cType/fType 셀렉트 포함.

## 변환(Set) 노드 + 종료 중복 제거 (2026-06-17)
- 종료(end): 같은 상류 노드는 1번만 수집(IF true/false 둘 다 종료 연결 시 중복 배열 방지).
- 변환(Set) 노드 추가: 상류 응답에서 JSONPath로 필드 추출/고정값으로 출력 객체 구성. 분기별로 다른 데이터를 내려줄 때 사용.
  - 엔진: transform 노드 params.setmap=[{key,mode:"path"|"literal",src/value}] → 출력 객체. setmap 없으면 기존(params 통과) 유지.
  - 프론트(editor.html 인라인+canvas.js): 로직 팔레트 5번째 "변환(Set)", transformHTML/addTransformNode, showProps 필드 행 편집(+추가/삭제), exportGraph 타입/라벨, loadWorkflow 복원. 토큰 --logic-transform, .xf/.set-row CSS.
- 권장 패턴: 시작→API→Switch($.data.aptcd)→(case별)변환→종료. 매칭 분기만 실행→종료에 단일 결과.
- 검증: pytest **40 passed**(변환 추출 1, 종료 중복 1 신규). e2e: aptcd 095001→{동,단지(095)}, 085001→{세대주,단지(085)} 확인.

## 실행창 자동주입 표시 + 체이닝 안내 (2026-06-17)
- 로직/하류 노드는 이전 노드 데이터를 **엣지 데이터 매핑**($.data.x → query.x)으로 받음. 매핑된 파라미터는 실행창에서 입력칸 대신 "← 이전 노드 데이터로 자동 주입"으로 표시(openRun + mappedTargets, .prow-auto).
- 주의(사용자 자주 실수): 스위치/조건 좌변은 상류 **응답값** 기준 → 요청 파라미터 `$.query.aptcd` 가 아니라 응답 `$.data.aptcd` 를 써야 함.
- 검증: pytest 40 passed. 엔진 e2e: start→switch($.data.aptcd)→api2(엣지매핑 $.data.aptcd→query.aptcd, $.data.dong→query.dong)→end 에서 api2 query={aptcd,dong} 주입 확인.

## 하류 노드 OUTPUT 자동 주입 (2026-06-17)
- 요구: 실행 시 모든 노드 파라미터를 다시 입력하지 말고, 하류 노드는 이전 노드 OUTPUT 값으로 처리.
- 엔진: api_call 의 미입력 파라미터(path/query/header 의 빈 값)를 **상류 첫 노드 출력에서 같은 이름으로 자동 주입**(_deep_find, 상위키 우선·중첩 탐색). 명시 data_mapping/정적값이 우선.
- 프론트(editor.html 인라인+canvas.js): 실행창이 **진입 노드(상류에 api/transform 없는 노드)만 입력 폼으로 표시**, 하류 API 개수는 "이전 노드 OUTPUT 자동 사용" 안내(run-note). hasUpstreamProducer로 판정.
- 클립보드: 비보안 컨텍스트(IP/HTTP) 대비 copyText+fallbackCopy(execCommand) 폴백 추가.
- 검증: pytest **41 passed**(자동 주입 1 신규). e2e: a1→switch($.data.aptcd)→a2(매핑 없음) 에서 a2 query={aptcd,dong} 자동 주입 확인.
