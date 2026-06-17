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
