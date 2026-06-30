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

## 감사 로그(Audit) — MCP/웹 실행 이력 (2026-06-17)
- 요구: 메인에서 MCP 호출 등 실행 이력을 audit 로그로 확인.
- DB: executions 에 source(web|mcp)·tool_name 컬럼 + 마이그레이션.
- 리포지토리: exec_repo.save(result, source, tool_name), list_recent(limit, source) (워크플로우명 JOIN), get() 에 source/tool_name.
- 기록: /run → source="web", MCP call_tool → exec_repo.save(source="mcp", tool_name) (같은 SQLite 파일 공유, MCP_DB_PATH 일치 필요).
- API: GET /api/executions(목록, ?source=mcp|web&limit=), GET /api/executions/{id}(상세).
- 화면: /logs (templates/logs.html, 자체 완결) — 출처 필터(전체/MCP/웹), 좌측 목록(출처·워크플로우·도구·시간·상태) · 우측 상세(노드별 INPUT/OUTPUT/ERROR). 메인 토픽바에 "📋 실행 로그" 링크. app.py /logs 라우트.
- 검증: pytest 41 passed. e2e: 웹+MCP 실행 저장→목록 2건(sources web/mcp, tool 표시), /·/logs 200.
- ★함정 재발: index.html topbar Edit가 파일 끝 truncate(끝 줄·{% endraw %}·닫는태그 소실, 실행 중 서버는 캐시 템플릿이라 정상처럼 보였음). bash로 꼬리 복원. 대형 인라인 템플릿은 Edit 후 반드시 raw/endraw 균형+inline JS node --check 확인.

================================================================
## ★ 최신 인수인계 요약 (2026-06-17, 이 섹션이 가장 최신)
================================================================

### 완료 상태 (모두 동작·검증됨, pytest 41 passed)
- 1~6단계: 스캐폴드/엔진/리포지토리/라우터/에디터/MCP 노출 + 메인 목록 — 완료.
- 7단계 제어 흐름: **분기(IF) · 스위치(Switch, 케이스 최대10+default) · 병합(Merge) · 필터(Filter) · 변환(Set)** — 완료.
- 조건 평가: 연산자 풀세트 + bool↔문자열 관용비교 + **우변 타입(rtype: auto/string/number/boolean/null)**.
- 실행 UX: **진입 노드만 입력**, 하류 노드는 상류 OUTPUT에서 동명 값 **자동 주입**(executor `_deep_find`; 명시 매핑·정적값 우선). 실행창에 자동주입 항목 표시(mappedTargets).
- 종료/결과: 단일 상류 통과(노드ID 래핑 제거)·동일 상류 중복 제거, 실행결과 `final` + MCP는 final만 반환.
- 실행 로그: 노드명·평가결과·INPUT/OUTPUT, hover 복사(execCommand 폴백).
- 리턴값 미리보기: `engine/schema_fields.py`로 응답스키마 $ref 평탄화 → 속성패널 JSONPath 목록/예시(클릭 복사).
- **감사 로그 `/logs`**: 웹/MCP 실행 이력(출처·도구명·시간·상태)+필터+상세. MCP call_tool 이 exec_repo.save(source="mcp", tool_name).

### 핵심 파일 포인터
- 엔진 로직 전부: `engine/executor.py` (노드 타입별 분기 처리·조건평가 `_typed_eq`/`eval_condition`·자동주입·final).
- 응답 평탄화: `engine/schema_fields.py` + `GET /api/operations/{id}/response-fields`.
- 감사 로그: `repositories/executions.py`(save/list_recent/get), `routers/executions.py`(GET /api/executions[/{id}]), `templates/logs.html`, app.py `/logs`.
- 프론트 동작: **`templates/editor.html`** (canvas.js·style.css **인라인** — 여기를 고쳐야 화면 반영됨), 참고용 사본 `static/canvas.js`·`static/style.css`.
- MCP: `backend/mcp_server.py` (stdio, 도구 빌드/호출/감사저장).

### 실행/검증
- 앱: `cd app && PYTHONPATH=. uvicorn backend.app:app --port 9000` (provider :9000).
- 더미 API: `PYTHONPATH=. uvicorn tools.dummy_api:app --port 8000`.
- 테스트: `PYTHONPATH=. python -m pytest tests -q` → **41 passed**.
- MCP Inspector: `npx @modelcontextprotocol/inspector .\.venv\Scripts\python.exe -m backend.mcp_server` (README 참고).

### ★ 반드시 지킬 함정 (메모리 web-mcp-provider-env 와 동일)
1. **Write/Edit 도구가 대형 파일을 디스크에서 truncate** → 큰 파일·다수 편집은 `bash cat > / python`로 정본 작성 후 `wc`/`node --check`/`ast.parse` 검증. (이번 세션에 index.html 끝이 잘려 복구함.)
2. **editor.html / index.html 은 CSS·JS 인라인** → static/ 만 고치면 화면 무반영. 두 곳 동기 또는 editor.html 직접 수정. 변경 후 `{% raw %}/{% endraw %}` 균형 + 인라인 JS node --check 필수.
3. **실행 중 uvicorn 은 Jinja 템플릿을 캐시** → 파일이 깨져도 화면은 정상처럼 보일 수 있음. 재시작 시 드러남.
4. **MCP 호출이 /logs 에 보이려면 MCP 서버·웹앱이 같은 DB**(MCP_DB_PATH 또는 기본 app/mcp_provider.db). 코드 변경 후 **MCP 클라이언트 재시작** 필요(도구목록·저장로직 반영).
5. 샌드박스: SOCKS 프록시(trust_env=False 기본), CDN 차단(vendor 로컬), bash 파일삭제 권한거부.

### 남은 백로그 (다음 세션 후보)
- **Loop/ForEach·Batch 노드**: 사이클 실행 필요 → executor 의 토폴로지 1패스 모델 재설계(서브그래프 반복). 별도 플랜 필요.
- **MCP 입력 스키마의 분기 인지**: 현재 build_input_schema 는 start 직결 api 노드만 스캔 → switch/merge 거친 하류 api 의 필수 파라미터는 누락될 수 있음.
- 실행 이력에서 재실행(replay), 로그 보존기간/페이지네이션, 변환 노드 타입 캐스팅 옵션.
- 시안 1:1 픽셀 미세조정(BUILD_GUIDELINES §8.5 육안 비교).

### 미커밋 주의
- git 커밋/푸시는 **로컬에서** 수행(샌드박스 .git 접근 불가). `.gitignore` 로 mcp_provider.db·__pycache__·.venv 제외.

================================================================
## ★★ MCP 입력 스키마 분기 인지 (2026-06-18, 이 섹션이 가장 최신)
================================================================

### 이번 주
- 백로그 "MCP 입력 스키마의 분기 인지" 해결. 원인→조치→검증→재발방지 순.
- **원인:** `backend/mcp_server.py build_input_schema` 가 start 에 **직접 연결된 노드만** 스캔 → switch/condition/merge/filter 를 거친 하류 api 노드의 필수 파라미터가 입력 스키마에서 누락 → MCP 클라이언트가 어떤 인자를 줘야 할지 알 수 없었음.
- **조치(executor 자동주입 로직과 정합):**
  - 스캔 범위를 start 에서 **전방 도달 가능한 모든 api 노드**로 확장(`_forward_reachable`).
  - **진입 api 노드만** 포함: 상류에 api/transform 생산자가 있으면 executor 가 동명 파라미터를 자동주입하므로 스키마에서 제외(`_has_upstream_producer`). 에디터 실행 UX(`hasUpstreamProducer`)와 동일 기준.
  - 정적값/엣지 `data_mapping` 으로 이미 채워진 파라미터 제외(`_norm_dest` 로 to 표현 정규화).
  - `required` 는 분기(condition/switch/filter)를 거치지 않고 **무조건 도달**하는 노드만(`_guaranteed_reachable`). 분기 하위 노드는 properties 에는 노출하되 required 에서 제외 → 과도제약 방지.
  - start 노드 없을 때는 기존 폴백(모든 api, op.required) 유지(하위호환).
- **검증:** `tests/test_mcp_schema.py` 신규 6케이스 — ①start→switch→api 하류 파라미터 노출(핵심 버그), ②start→api required, ③하류 생산자 노드 자동주입 제외, ④정적값 제외, ⑤엣지매핑 제외, ⑥apply_tool_args 라운드트립. **전체 pytest 47 passed**(기존 41 + 신규 6, 회귀 없음).

### 사용자 테스트(콘솔 / URL)
콘솔(앱 디렉터리 `app/`, venv 활성화 후):
```powershell
# 1) 단위 테스트 — 47 passed 확인
$env:PYTHONPATH="."; python -m pytest tests -q
# (분기 인지만) python -m pytest tests/test_mcp_schema.py -q

# 2) MCP Inspector 로 입력 스키마 육안 확인
npx @modelcontextprotocol/inspector .\venv\Scripts\python.exe -m backend.mcp_server
```
URL(에디터에서 분기 워크플로우 구성 후):
1. `http://localhost:9000/` → 워크플로우 생성 → `/editor/{id}`.
2. 시작 → 분기(IF) 또는 스위치 → API 노드 연결(API 가 분기 **직후 첫 노드**가 되도록). API 필수 파라미터는 비워둠.
3. 저장(PUT) → 메인에서 MCP 노출(expose) 토글.
4. MCP 클라이언트(또는 Inspector) **재시작** → 도구 입력 스키마에 그 API 의 파라미터(`<node_id>.query.<param>` 등)가 **나타나는지** 확인(수정 전에는 누락).

### 핵심 파일 / 신규 헬퍼
- `backend/mcp_server.py`: `_norm_dest`, `_forward_reachable`, `_guaranteed_reachable`, `_has_upstream_producer`, 재작성된 `build_input_schema`.
- `tests/test_mcp_schema.py`(신규, `pytest.importorskip("mcp")` 로 mcp 미설치 환경 스킵).

### 이슈 / 리스크
- 분기 하위 진입 api 의 필수 파라미터는 **required 가 아닌 optional** 로 노출됨(런타임 분기 선택 의존). 클라이언트가 해당 분기를 타는 인자를 제공해야 실제 호출됨. 의도된 동작.
- MCP 도구 목록·스키마는 서버 기동 시 1회 → **변경 후 MCP 클라이언트 재시작 필요**(기존과 동일).
- ★함정 재발: **Edit 직후 bash 마운트가 mcp_server.py 구버전(꼬리 누락 158줄)을 stale 캐싱**. 실제 디스크(Read 도구 기준)는 정상 276줄. 런타임 검증은 `/tmp` 복사본에서 수행(메모리 [[web-mcp-provider-env]] 와 동일). 단위 테스트는 정상 통과.

### 다음 주 계획(잔여 백로그)
- Loop/ForEach·Batch 노드(executor 토폴로지 1패스 → 서브그래프 반복 재설계, 별도 플랜).
- 실행 이력 재실행(replay)·페이지네이션, 시안 1:1 픽셀 미세조정(BUILD_GUIDELINES §8.5).
- (선택) merge 노드 하류 진입 api 의 required 정밀화 — 현재는 보수적으로 optional 처리.

### 미커밋 주의(재확인)
- 본 변경은 `backend/mcp_server.py`, `tests/test_mcp_schema.py` 2파일. git 커밋/푸시는 **로컬에서** 수행.

================================================================
## ★★★ 실행 로그 페이징 + 검색 (2026-06-18, 이 섹션이 가장 최신)
================================================================

### 이번 주
- `/logs`(감사 로그) 화면에 **페이지네이션 + 검색** 추가.
- **리포지토리**(`backend/repositories/executions.py`):
  - `_filter_clause(source, q)` 신규 — source 필터 + 검색어 WHERE 절 생성. 검색 대상 = 워크플로우명(`w.name`)·도구명(`e.tool_name`)·상태(`e.status`)·실행ID(`CAST(e.id AS TEXT)`) LIKE.
  - `list_recent(limit, offset, source, q)` — `offset`·`q` 추가(ORDER BY id DESC LIMIT ? OFFSET ?).
  - `count_recent(source, q)` 신규 — 페이징 메타용 총 건수(JOIN 포함, 워크플로우명 검색 위해).
- **라우터**(`backend/routers/executions.py`): `GET /api/executions` 응답이 **list → `{items, total, limit, offset}`** 로 변경. 쿼리 `limit`(기본50·상한200 클램프)·`offset`·`source`·`q`.
- **프론트**(`templates/logs.html`, 자체 완결): 검색 입력(300ms 디바운스) + 하단 페이지네이션(이전/다음·`page/pages·총 N건`). 페이지 크기 50. 출처/검색 변경 시 offset 0으로 리셋. `renderPager()` 추가, `loadList()` 가 새 응답형식(`data.items`/`data.total`) 사용.

### 검증
- 신규 `tests/test_logs.py` 5케이스 — ①페이징(7건→3/3/1, id DESC·무중복), ②출처필터, ③검색(도구명/상태/워크플로우명/조합/무매칭), ④ID검색, ⑤API 응답형식(items/total/limit/offset·offset 페이지·limit 상한 클램프).
- **전체 pytest 52 passed**(기존 47 + 신규 5, 회귀 없음). logs.html 인라인 JS `node --check` 통과, `{% raw %}/{% endraw %}` 균형·닫는 태그 정상(Read 도구 기준).

### 사용자 테스트(콘솔 / URL)
콘솔(`app/`):
```powershell
$env:PYTHONPATH="."; python -m pytest tests -q          # 52 passed
$env:PYTHONPATH="."; python -m pytest tests/test_logs.py -q
$env:PYTHONPATH="."; uvicorn backend.app:app --port 9000
```
URL:
1. `http://localhost:9000/logs` 접속.
2. 상단 검색창에 워크플로우명·도구명·상태(success/failed)·실행ID 입력 → 300ms 후 자동 필터.
3. 출처 세그먼트(전체/웹/MCP) 전환 시 첫 페이지로.
4. 목록 하단 **이전/다음** 으로 페이지 이동, `현재/전체 페이지 · 총 N건` 표시 확인.
   (API 직접 확인: `GET /api/executions?limit=50&offset=0&source=mcp&q=impo` → `{items,total,limit,offset}`.)

### 이슈 / 리스크
- **API 응답 형식 변경**(list → 객체). 기존 소비자는 `/logs`(logs.html)뿐이며 함께 갱신됨. 외부에서 `/api/executions` 를 list 로 파싱하던 코드가 있으면 `.items` 로 수정 필요.
- 검색은 단순 LIKE(부분일치, 대소문자: ASCII 무시·한글 그대로). 인덱스 없음 → 데이터 大 시 성능 고려(executions.id 정렬은 PK라 양호).
- ★함정 재발(동일): **Edit/Write 직후 bash 마운트가 편집 파일을 stale/truncate 캐싱**. 이번에도 `routers/executions.py`(items 누락)·`repositories/executions.py`(get() 잘림)·`logs.html`(endraw 누락 167줄)가 마운트에서 깨져 보였으나 **실제 디스크(Read 도구)는 모두 정상**. 검증은 `/tmp` 복사본에 정본을 덮어써 수행(메모리 [[web-mcp-provider-env]]).

### 다음 주 계획(잔여 백로그)
- 실행 이력 재실행(replay), 로그 보존기간 정책.
- Loop/ForEach·Batch 노드(별도 플랜), 시안 1:1 픽셀 미세조정(BUILD_GUIDELINES §8.5).
- (선택) 검색 고도화: 날짜 범위 필터, 상태 칩 필터.

### 미커밋 주의(재확인)
- 본 변경 4파일: `backend/repositories/executions.py`, `backend/routers/executions.py`, `templates/logs.html`, `tests/test_logs.py`. git 커밋/푸시는 **로컬에서** 수행.

## 호출 URL 노출 (2026-06-25 추가)

목적: ① 워크플로우 **선택화면 목록**에서 각 워크플로우가 *어디를 호출하는지*, ② **에디터 화면**에서 각 API 노드가 *어떤 URL을 호출하는지* 보이도록.

### 이번 주 (이번 세션 완료분)
- 백엔드 `repositories/workflows.py`: `list_all()` 응답에 `endpoints`(노드별 `{method, path, url}`, 중복 제거) 추가. URL 우선순위는 executor와 동일하게 `node.base_url → operation.base_url → DEFAULT_BASE_URL`, `engine.http_client.build_url`로 조합. 헬퍼 `_endpoints()` 신설.
- `backend/models.py`: `WorkflowSummary`에 `endpoints: list[dict]` 필드 추가.
- `backend/app.py`: `/editor/{id}` 렌더 컨텍스트에 `default_base_url`(=`DEFAULT_BASE_URL`) 주입.
- `templates/index.html`: 카드에 호출 엔드포인트 목록(메서드 배지 + 전체 URL, 최대 3개 + "외 N개") 표시. `.calls/.call-row/.call-url` 스타일 추가.
- `templates/editor.html`: ① API 노드 카드에 호출 URL 줄(`.nurl`, 링크 아이콘+URL) 추가, ② 속성 패널에 읽기전용 **호출 URL**(Base URL 입력 시 실시간 갱신) + 적용 시 노드 카드 URL 동기화. `slimOp`에 `base_url` 포함, JS 헬퍼 `joinUrl/effUrl` 추가, 템플릿에 `var DEFAULT_BASE_URL` 주입.

### 검증
- 콘솔: `/tmp` 복사본에서 `pytest` **52 passed**(회귀 없음).
- TestClient: `GET /api/workflows` → WF#1 endpoints에 `GET http://localhost:8000/impo/detail`, `/recp/status`, `/insp/status` 정상 노출. `/editor/1` 렌더에 `DEFAULT_BASE_URL = "http://localhost:8000"` 및 `effUrl` 함수 포함 확인.
- 사용자 테스트(로컬): `cd app && python -m uvicorn backend.app:app --port 9000` 후 → 목록 `http://localhost:9000/` (카드 호출 URL 확인), 에디터 `http://localhost:9000/editor/1` (노드/속성 패널 URL 확인).

### 이슈 / 리스크
- 표시 URL은 **실행 시 base_url 결정 로직과 동일 규칙**으로 계산되나, 실제 실행 시점의 환경변수 `MCP_DEFAULT_BASE_URL`이 다르면 표시값도 따라감(서버 기동 시점 기준). 노드별 Base URL 오버라이드가 있으면 그 값을 우선 표시.
- 함정 재발(동일): Edit/Write 직후 **bash 마운트 READ 캐시가 truncate/stale**(app.py `return render(`에서 끊김, workflows.py `conn.close()`→`conn.cl`). 실제 디스크(Read 도구)는 정상. 우회: `mv f f.cb && mv f.cb f` 캐시버스트 후 `/tmp` 복사·검증. 메모리 [[web-mcp-provider-env]].

### 다음 주 계획
- (선택) 선택화면 카드 URL을 호스트만 축약 표시하는 옵션 / 동일 호스트 그룹핑.
- 팔레트 항목에도 호스트 표기 여부 검토(현재 path만).

### 미커밋 주의
- 본 변경 5파일: `backend/repositories/workflows.py`, `backend/models.py`, `backend/app.py`, `templates/index.html`, `templates/editor.html`. git 커밋/푸시는 **로컬에서** 수행.

## 멀티 API 관리/호출 (2026-06-25 추가)

목적: 단일 스펙(specs[0])만 쓰던 구조를 **여러 API를 한 곳에서 관리·호출**하도록 확장. ① API URL·인증 1회 관리, ② 에디터에서 API 선택 시 오퍼레이션 목록 전환, ③ 워크플로우 카드에 다중 API 호출 표시(URL 미표시), ④ 추천기능(연결 테스트·노드 API 칩·통합검색·스펙 재동기화) 포함.

### 핵심 설계
- **`connections`(API 연결) 엔티티 신설** = base_url + 인증을 관리하는 단위. `specs.connection_id`로 스펙이 연결에 소속(연결 1개에 스펙 여러 개 가능). 기존 스펙은 `db._backfill_connections()`로 1:1 자동 편입(멱등).
- **실행 일원화**: `specs_repo.get_operation()`이 op→spec→connection 조인으로 `conn_base_url`/`auth`(원본 시크릿) 반환. executor 우선순위 — base_url `node→connection→operation→DEFAULT`, auth `connection→실행시 입력(폴백)`. 이로써 **MCP 노출 호출(기존 `auth=None`)에도 연결 인증이 자동 적용**됨.
- **인증 시크릿**: DB 평문 저장 + 응답 마스킹(`connections.mask_auth`, 마스킹값 `••••••••`). 편집 시 마스킹값 그대로 저장하면 기존 값 유지(`_merge_secrets`). 원본은 `get_auth()`/`get_operation()`만 반환.

### 이번 주 (이번 세션 완료분)
- **DB**(`db.py`): `connections` 테이블, `specs.connection_id` 컬럼/마이그레이션, 기존 스펙 백필.
- **리포지토리**: `repositories/connections.py` 신설(CRUD·마스킹·`get_auth`·`list_operations`), `specs.py`(연결 자동생성, `resync_operations`, `get_spec`, get_operation 조인), `workflows.py`(list_all에 `apis` 추가).
- **라우터/모델**: `routers/connections.py`(GET/POST/PUT/DELETE, `/test`, `/operations`), `specs.py`(`connection_id` 인자, `/specs/{id}/resync`), `models.py`(Connection·apis·SpecUploadResult.connection_id), `app.py`(connections 라우터 등록).
- **엔진**: `executor.py` base_url/auth 우선순위 적용. 단위테스트 `test_connection_base_url_and_auth_resolution` 추가.
- **에디터**(`editor.html`): 팔레트 **API 선택 드롭다운**(localStorage 기억), **전체 API 통합검색**(API명 그룹), 노드 카드 **API 이름 칩**. 전체 연결 오퍼레이션을 `OPS_ALL`/`opsById`로 1회 로드.
- **홈**(`index.html`): 상단 **API 관리 모달**(base_url·인증 편집·마스킹·**연결 테스트**·스펙 **URL 재동기화**), 워크플로우 카드를 **"API N개 호출 · 이름…"**으로 변경(URL 제거).

### 검증
- 콘솔: `/tmp` 복사본 `pytest` **53 passed**(executor 인증/URL 테스트 1건 추가, 회귀 없음).
- TestClient: connections 목록/CRUD/마스킹, `/connections/{id}/operations`(conn3=405), workflows `apis`, 홈 `apiMgrBtn`+모달, 에디터 `apiSelect` 렌더, `/connections/{id}/test` graceful 실패(네트워크 차단 환경) 확인.
- 마이그레이션: 기존 4개 스펙 → 연결 4개 자동 생성, op 카운트 일치(17/17/405/17).
- 사용자 테스트(로컬): `cd app && python -m uvicorn backend.app:app --port 9000`
  - 홈 `http://localhost:9000/` → 우상단 **API 관리**에서 base_url·인증 설정/연결 테스트/재동기화, 카드의 "API N개" 확인.
  - 에디터 `http://localhost:9000/editor/1` → 좌측 **API** 드롭다운 전환·검색창 통합검색, 노드 API 칩 확인.

### 이슈 / 리스크
- **인증 토큰 DB 평문 저장**(사용자 결정: DB 저장 + UI 마스킹). DB 파일/백업 유출 시 토큰 노출 → 운영 전 환경변수 참조 방식 전환 권장(후속 백로그).
- 첫 서버 기동 시 `init_db()`가 `connections` 생성 + 기존 스펙 백필을 수행(멱등). 기동 후 `/api/connections`로 확인.
- 연결 테스트는 `base_url` 루트(GET)로 핑 — 헬스 엔드포인트가 따로면 404가 나도 "연결됨"으로 볼 수 있음(상태코드 함께 표시).

### 다음 주 계획
- 인증 시크릿 환경변수 참조(`${ENV}`) 옵션, 연결별 헬스 경로 지정.
- 노드가 어느 연결에 속하는지 우측 속성 패널에도 표기, 워크플로우 내 API 혼용 경고.
- 스펙↔연결 재배정 UI(여러 스펙을 한 연결로 병합).

### 미커밋 주의(멀티 API)
- 변경/신규: `backend/db.py`, `backend/models.py`, `backend/app.py`, `backend/repositories/connections.py`(신규), `backend/repositories/specs.py`, `backend/repositories/workflows.py`, `backend/routers/connections.py`(신규), `backend/routers/specs.py`, `engine/executor.py`, `tests/test_executor.py`, `templates/index.html`, `templates/editor.html`. git 커밋/푸시는 **로컬에서** 수행.

### API 삭제(사용처 경고) — 추가분
- `GET /api/connections/{id}/usage` — 이 API를 호출하는 워크플로우 목록/개수 + 영향 노드 수.
- `DELETE /api/connections/{id}` — 연결+스펙+오퍼레이션 완전 삭제(되돌릴 수 없음). 삭제 대상 오퍼레이션을 참조하던 **노드는 보존하되 `operation_id`를 NULL로 해제**(FK 위반 회피, 사용자 재지정 필요). 반환: `{affected_workflows, detached_nodes}`. `connections.list_all`에 `workflow_count` 추가.
- 홈 'API 관리' 모달의 각 API 카드에 **삭제** 버튼 → usage 조회 후 "워크플로우 N개(이름…) 노드 M개 연결 해제 · 되돌릴 수 없음" 확인창(`connDelOverlay`) → 삭제.
- 검증: pytest 53 passed, 시드 DB로 usage/delete 캐스케이드(노드 해제·스펙/op/연결 제거) 확인, 홈 삭제 UI 렌더 확인.

## 더미 API 쓰기 메서드 + 독립 프로젝트 분리/Docker화 (2026-06-30 추가)

### 이번 주
- 더미 API(`dummy_api.py`)에 MCP 워크플로우 테스트용 **쓰기 메서드 추가**: `PUT/PATCH/DELETE /users/{id}`, `POST/GET /users`, `PUT/PATCH/DELETE /orders/{id}`. 인메모리 저장(재기동 시 사용자 1·2로 리셋). PUT=전체교체(upsert), PATCH=부분수정(`exclude_unset`), DELETE/없는 리소스=404.
- **`tools/`를 `app/`과 동일 레벨의 독립 프로젝트로 분리.** 더미 API 는 app 코드를 import 하지 않는 standalone(grep 확인) → app venv/PYTHONPATH 불필요. 실행 모듈명이 `tools.dummy_api:app` → **`dummy_api:app`** 로 변경.
- **Docker화**: `tools/`에 `Dockerfile`(python:3.11-slim, CMD `uvicorn dummy_api:app --host 0.0.0.0 --port 8000`), `requirements.txt`(fastapi/uvicorn[standard]/pydantic), `.dockerignore`, `README.md`(로컬·Docker 실행법) 추가.

### 검증 (콘솔)
- `/tmp` 복사본에서 ast OK, `python -m uvicorn dummy_api:app` 기동 성공, `/health`·PUT·PATCH·DELETE·POST 라이브 호출 + 404 정상, OpenAPI 에 `GET/POST/PUT/PATCH/DELETE` 노출 확인.
- Docker 빌드는 **샌드박스에 docker 미설치** → 사용자 로컬에서 수행 필요. CMD 라인은 동일 커맨드로 검증 완료.

### 사용자 테스트 (콘솔 / URL)
```bash
cd tools
uvicorn dummy_api:app --host 0.0.0.0 --port 8000        # 또는 docker build -t dummy-api . && docker run --rm -p 8000:8000 dummy-api
```
- URL: http://localhost:8000/docs 에서 PUT/PATCH/DELETE "Try it out". curl 예시는 `tools/README.md` 및 `app/TESTING.md` §2-1.

### 이슈 / 리스크 · 조치
- **★ 기존 `app/tools/` 잔존**: 샌드박스는 파일 삭제 권한이 없어(rm Operation not permitted) 옛 폴더를 못 지웠음. **로컬에서 수동 삭제 필요**:
  `Remove-Item -Recurse -Force app\tools`  (정리 안 하면 옛 경로 `tools.dummy_api`로 잘못 기동할 수 있음)
- Provider(:9000)에서 새 메서드 쓰려면 dummy 스펙 **재등록**(`POST /api/specs/from-url`, url=`http://localhost:8000/openapi.json`) 필요 — 그래야 PUT/PATCH/DELETE 오퍼레이션이 잡힘.
- 인메모리 저장 → 영속 필요 시 후속에서 SQLite/파일 백엔드 검토.

### docker compose 추가 (2026-06-30)
- `tools/docker-compose.yml` 신설: `dummy-api` 서비스(build `.`, 포트 8000:8000, `restart: unless-stopped`, healthcheck=python urllib `/health`). 실행 `cd tools && docker compose up --build`(-d 백그라운드, down 종료).
- 검증: YAML 파싱 OK(샌드박스 docker 미설치 → 실제 `compose up`은 로컬에서). README 갱신.
- **호스트 포트 18000 매핑(2026-06-30)**: 로컬 8000 충돌(`address already in use`)로 `ports: "18000:8000"` 변경. 접속 http://localhost:18000. 컨테이너 내부·healthcheck·dummy_api.py 는 8000 유지.
  - ⚠️ 주의: dummy_api.py 의 OpenAPI `servers[].url` 은 여전히 `http://localhost:8000`. Provider(:9000)에서 워크플로우로 호출 시 base_url 이 8000으로 잡히므로, 18000으로 띄웠다면 스펙 등록 후 연결/노드 base_url 을 `http://localhost:18000` 로 지정하거나 `MCP_DEFAULT_BASE_URL` 조정 필요.

### 다음 주 계획
- (선택) tools/에 pytest 스모크 테스트 추가, app도 Dockerfile화하여 compose로 app+tools 동시 기동.

## 더미 API 전면 재작성 — XpERP 입주자 관리 (2026-06-30 추가)

### 이번 주
- 사용자 제공 `STT_API설계_분석.xlsx`(통화 13,409건 분석) 기반으로 더미 API 를 **XpERP 입주자 관리 전체 API 로 전면 재작성**. 기존 users/orders 제거.
- 9개 그룹·20개 엔드포인트 구현: IMPO(/impo/detail), RECP(/recp/unpaid·unpaid/list·status·detail), INSP(/insp/status·usage·missing), OCCP(/occp/unit·list + POST/PUT/PATCH/DELETE), CMPL(/cmpl/list·{id}), ACCT(/acct/summary·budget), HR(/hr/staff), PARK(/park/vehicle), /health.
- 설계서의 필수/선택 파라미터·응답 구성 그대로 반영. 공통 `aptcd`(6자리)·`yearmon`(YYYYMM). 시드 단지 `001023`(세대5·직원4·민원3, 미납 2세대·전출 1세대 포함).
- **입주자(OCCP)에 쓰기 메서드 유지**(앞선 PUT/PATCH/DELETE 요구 충족): 등록/전체교체/부분수정(전출 처리)/삭제. 검증 — aptcd 6자리 400, 없는 세대 404, 필수 누락 422, type/status 허용값 외 400.

### 검증 (콘솔)
- ast OK(566줄), uvicorn 기동 후 20개 엔드포인트 전부 라이브 호출 성공. OpenAPI 노출 확인.
- 예: `/impo/detail`(101-305 총 128,000원·항목별), `/recp/unpaid?months=3`(미납 1세대), `/occp/list?status=전출`(최강 1세대), OCCP POST→PATCH(전출)→PUT→DELETE 라운드트립.
- ★주의(검증 함정): curl 에 **한글 쿼리값을 인코딩 없이** 넣으면 빈 응답/422 → `-G --data-urlencode` 사용. API 자체는 정상.

### 사용자 테스트 (콘솔 / URL)
```bash
cd tools
uvicorn dummy_api:app --host 0.0.0.0 --port 8000        # 또는 docker compose up --build (호스트 18000)
```
- URL: http://localhost:8000/docs 에서 그룹별(IMPO/RECP/INSP/OCCP/CMPL/ACCT/HR/PARK) "Try it out". 한글값은 Swagger UI 가 자동 인코딩.
- Provider 연동: `POST /api/specs/from-url`(url=openapi.json) 재등록 → 시드 워크플로우의 `/impo/detail`·`/recp/status`·`/insp/status` 와 경로 일치.

### 이슈 / 리스크
- 인메모리 → 재기동 시 OCCP 쓰기 결과 리셋. 영속 필요 시 후속.
- yearmon 은 에코만 하고 데이터는 단지 시드값 고정(월별 변동 없음). 회계/예산은 고정 샘플.
- 18000 매핑 시 OpenAPI `servers[].url`(8000)과 불일치 → base_url 지정 필요(앞 섹션 참고).

### 미커밋 주의
- 변경: `tools/dummy_api.py`(전면 재작성), `tools/README.md`. git 커밋/푸시 + 옛 `app/tools/` 삭제는 **로컬에서**.

## 추가 (2026-06-30) — 원격 Swagger 수정 + 아파트명→코드 조회 API
- **Swagger "Try it out" Failed to fetch 수정**: 스펙 `servers` 가 `http://localhost:8000` 하드코딩 → HTTPS/DDNS 접속 시 혼합콘텐츠로 차단. `servers` 를 `DUMMY_PUBLIC_URL` 환경변수 기반(미설정 시 비워 relative=현재 origin)으로 변경 + `CORSMiddleware`(allow `*`) 추가. 검증: 기본 openapi 에 servers 키 없음, OPTIONS 200·ACAO `*`.
- **단지 레지스트리 + 조회 API**: `_APARTMENTS`(5개 단지, 명↔코드↔주소). `GET /apt/code?name=`(부분일치, 단건이면 `aptcd` 최상위 반환 → 후속 API 체이닝용), `GET /apt/list`. 검증: 래미안→002099 단건, "아파트"→4건, 무매칭 count 0, name 누락 422.
- 재배포: `cd tools && docker compose up -d --build` 후 docs 하드 리로드(Ctrl+Shift+R).

## 추가 (2026-06-30) — /apt/code 되묻기 힌트 필드
- 목적: 발화로 단지코드 미확정 시 챗봇이 사용자에게 추가 입력을 요청(되묻기)하도록 신호 제공. 판단은 LLM, 신호는 더미 API.
- `/apt/code` 응답에 `resolved`(확정 여부)·`needs_input`(되묻기 필요)·`reason`(ok/ambiguous/not_found)·`message`(안내 문구) 추가. 단건이면 기존대로 `aptcd`·`name` 최상위 반환.
- 검증: 단건(강변래미안→resolved=true·aptcd 002099), 다건("아파트"→needs_input=true·reason=ambiguous·후보4), 무매칭(reason=not_found) 확인.
- 문서: `tools/README.md` 에 "챗봇 되묻기(needs_input) 설계" 섹션 추가(필드표·분기별 응답·권장 흐름·422/400 2차 트리거).
- 미반영(대기): 강변래미안(002099) 등 비-001023 단지의 세대 시드 데이터 — 필요 시 추가하면 명→코드→/impo/detail 전체 데모가 실데이터로 동작.

## MCP 도구 목록 동적 갱신 (재시작 불필요화) (2026-06-30)

### 이번 주
- 요구: "워크플로우 추가/변경 때마다 Claude 데스크탑 재시작" 해소. 다중 소비자(챗봇 등) 환경 고려해 부하 최소화.
- **변경 감지 캐시**: `wf_repo.change_signature(group)` 신설 — 노출 워크플로우의 `(COUNT, MAX(updated_at))` 1쿼리. 노출 토글·그래프 저장·이름/그룹 변경은 updated_at 갱신, 생성/삭제/노출해제는 COUNT 변동 → 이 시그니처로 전부 감지.
- `mcp_server.ensure_tools(force)`: 시그니처가 바뀐 경우(또는 force)에만 `build_tools()` 재실행, 아니면 가벼운 1쿼리만. `list_tools` 핸들러가 매 호출 `ensure_tools()` → **새 연결/재조회는 항상 최신**(서버 재시작 불필요).
- **listChanged 알림**: `create_initialization_options(notification_options=NotificationOptions(tools_changed=True))` 로 capability 광고. 백그라운드 폴러 `_poll_changes`(MCP_POLL_SECS, 기본 5초)가 변경 감지 시 `list_tools`에서 캡처한 세션으로 `send_tool_list_changed()` → **이미 연결된 지원 클라이언트도 재시작 없이 갱신**. `MCP_POLL_SECS=0`이면 폴러 끔.
- 부하: list_tools는 연결/재조회 시점에만 호출(매 사용자 요청 아님) + 변경 없으면 집계 1쿼리뿐. 실제 부하 병목은 call_tool 실행·SQLite 동시쓰기·stdio 모델 쪽(대규모면 HTTP/SSE + RDS 전환 권장).

### 검증 (콘솔)
- ast OK(양 파일), `change_signature` 실DB: 노출 WF 수정 시 시그니처 변동 확인.
- `ensure_tools`: 초기 force=True 빌드(2도구), 변경없음→False(재빌드 안함), 노출 WF updated_at 변경→True(재빌드). init options `tools.listChanged=True` 광고 확인.
- 회귀: `pytest tests -q` → **58 passed**(기존 + 신규, mcp/test_api 포함).

### 사용자 테스트 (콘솔 / URL)
- MCP Inspector 로 갱신 확인: `npx @modelcontextprotocol/inspector .\venv\Scripts\python.exe -m backend.mcp_server` 실행 → 워크플로우 노출 토글 변경 → 수 초 내(기본 5초) 도구 목록 자동 갱신되는지(또는 재조회 시 반영) 확인.
- Claude 데스크탑: listChanged 지원 시 재시작 없이 갱신. 미지원이면 커넥터 토글 또는 재조회로 반영.

### 이슈 / 리스크
- listChanged 자동 반영은 **클라이언트 지원에 의존**(Claude 데스크탑 실동작은 사용자 확인 필요). 폴백은 "재조회/재연결 시 ensure_tools 가 최신 빌드".
- 백그라운드 세션 참조는 `list_tools` 1회 호출 후에 잡힘(클라이언트가 초기 list 호출하므로 정상 흐름). 알림 전송 실패는 조용히 무시(안정성 우선).
- 변경 시그니처는 노출 WF 한정(group 포함) → 비노출 WF 편집은 알림 트리거 안 함(과알림 방지).

### 미커밋 주의
- 변경: `backend/mcp_server.py`, `backend/repositories/workflows.py`. git 커밋/푸시는 **로컬에서**. MCP 코드 변경이므로 Claude 확장(또는 MCP 서버) **1회 재시작**해야 새 로직이 적용됨(이후부터는 재시작 불필요).

## API 재동기(resync) 500 수정 — FK 위반 + 노드 연결 끊김 (2026-06-30)
- 증상: `POST /api/specs/{id}/resync` → `sqlite3.IntegrityError: FOREIGN KEY constraint failed` (specs.py `DELETE FROM operations`).
- 원인: resync 가 operations 를 통째 DELETE 후 재INSERT. ① 워크플로우 노드가 operation 을 FK 참조 → DELETE 거부, ② 재삽입 시 PK(id) 변경 → 노드 operation_id 연결 끊김.
- 조치: `resync_operations` 를 **(method, path) 기준 업서트**로 재작성. 동일 엔드포인트는 기존 id 유지 UPDATE(노드 연결 보존), 신규는 INSERT, 사라진 것만 **노드 detach(operation_id=NULL) 후 DELETE**. 반환에 added/updated/removed/detached_nodes 추가.
- 검증: spec 6 동일 raw resync → FK 오류 없음, 노드 280→op 520(/impo/detail) 연결 유지, 21개 updated·삭제 0, get_operation 유효. `pytest tests -q` **58 passed**(회귀 없음).
- 미커밋: `backend/repositories/specs.py`. git 커밋/푸시는 로컬에서. (웹앱 변경이므로 provider :9000 재시작 후 반영.)

## 에디터 입력 매핑 UI + 더미 API 응답 모델(리턴값 미리보기) (2026-06-30)

### 이번 주
- **이슈A 다운스트림 노드 입력 매핑**: 기존엔 엣지(연결선) 클릭 → 원시 JSON 배열로만 매핑 가능 → 발견·사용 어려움.
  - `templates/editor.html`(인라인) `showProps` api 분기에 **"입력 매핑" 섹션** 추가. 노드를 클릭하면 그 노드의 파라미터(path/query/header)별로 상류 응답 JSONPath(`from`)를 입력 → 들어오는 생산자 엣지의 `edgeMap[src->tgt]`에 `{from,to}`로 기록.
  - 신규 헬퍼: `incomingProducerKey`(상류 생산자 엣지 키), `nodeParamTargets`(전체 op params_schema에서 대상), `inputMappingSection`(HTML), `bindInputMapping`(적용). `fullOp = opsById[op.id]`로 params_schema 확보(slimOp는 스키마 미보유). `.map-row/.map-to/.map-from` CSS 추가.
  - 기존 엣지 클릭 매핑(showEdgeProps)도 그대로 유지(둘 다 같은 edgeMap 사용).
- **이슈B 리턴값 미리보기 빈 값**: 원인 = 더미 API 엔드포인트가 response_model 미선언 → OpenAPI 응답 스키마 `{}` → `response_fields`가 필드 0개(note만). 
  - `tools/dummy_api.py`에 Pydantic 응답 모델 추가(Apt/Impo/Recp/Insp/Occp목록/Cmpl/Acct/Hr/Park) + 각 GET에 `response_model=`. (occp/unit은 단건·목록 가변 반환이라 제외.)

### 검증
- 더미 API: ast OK, 기동 후 openapi에 `$ref: ImpoDetailResp` 등 노출, 전 GET 라이브 200(모델 일치). `schema_fields.response_fields`로 `/impo/detail` **12필드**(`$.items[0].dong` 등 중첩) 추출 확인 → 재동기 후 에디터 미리보기 채워짐.
- 에디터: 인라인 JS `node --check` 통과, `{% raw %}/{% endraw %}` 1/1, `/editor/1` 200 + "입력 매핑"·신규 함수 포함. `pytest tests -q` **58 passed**(회귀 없음).

### 사용자 적용 절차
1. 더미 API 재배포: `cd tools && docker compose up -d --build`.
2. provider(:9000)에서 해당 스펙 **재동기**(API 관리 → 재동기) → 응답 스키마 반영. provider 코드 변경(editor.html) 반영 위해 provider도 재시작.
3. 에디터에서 ① API 노드 클릭 → "입력 매핑"에 상류 응답 경로 입력(예 `$.aptcd`→`query.aptcd`), ② 같은 패널 하단 "리턴값 미리보기"에서 필드 클릭 시 JSONPath 복사.

### 이슈 / 리스크
- 입력 매핑 섹션은 **상류에 api/transform 생산자 연결이 있을 때만** 표시(진입 노드는 직접 params 입력). 다중 상류면 첫 생산자 엣지에 기록.
- occp/unit은 응답 모델 미적용(가변 반환) → 미리보기는 note 표시. 필요 시 단건/목록 분리.
- editor.html 인라인이 정본 → static/canvas.js 미동기(기존 함정과 동일, 화면은 editor.html 반영).

### 미커밋
- 변경: `templates/editor.html`, `tools/dummy_api.py`. git 커밋/푸시는 로컬에서.

### 미커밋 주의
- 신규: `tools/dummy_api.py`(이동), `tools/Dockerfile`, `tools/requirements.txt`, `tools/.dockerignore`, `tools/README.md`. 갱신: `app/TESTING.md`, `app/HANDOFF.md`, `README.md`. 옛 `app/tools/` 삭제 + git 커밋/푸시는 **로컬에서** 수행.
