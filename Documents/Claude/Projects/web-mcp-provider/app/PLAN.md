# 빌드 플랜 — MCP Provider (사양서 §9 기반)

원칙: **각 단계 = 플랜 구성 → 순차 실행 → 핸드오프**. 단계마다 로컬 브라우저/엔드포인트로 검증.
기술 스택 고정: FastAPI + Jinja2 + htmx + Drawflow + SQLite (빌드 도구 없음, CDN/정적).

## 단계별

### 1단계 — 스캐폴드 ✅ (이번 세션)
- 산출물: `backend/app.py`(lifespan→init_db, 라우터 등록, 정적/템플릿 마운트), `backend/db.py`(멱등 DDL + `_apply_column_migrations`), `backend/models.py`(Pydantic 와이어 모델).
- 검증: 앱이 import/기동되고 `GET /healthz` 200, DB 파일 생성 + 7개 테이블 존재.

### 2단계 — 엔진 + 단위 테스트 ✅ (이번 세션)
- 산출물: `engine/parser.py`(OpenAPI v2/v3 → operations + base_url 규칙), `engine/http_client.py`(base_url 우선순위·프로토콜 가드·인증 주입), `engine/executor.py`(검증·토폴로지·순차 실행·노드 로그).
- 계약(사양서 §4):
  - base_url 우선순위: `node.base_url → operation.base_url → DEFAULT_BASE_URL`.
  - 노드 실패 시 raise 안 함 → 해당 노드 `failed`, 이후 `skipped`.
  - JSONPath 부분집합: `$`, 점 접근, 인덱스.
- 검증: `pytest tests` 전체 통과(parser v2/v3, base_url 우선순위, 프로토콜 가드, 순차 실행+스킵, JSONPath).

### 3단계 — 라우터 + 리포지토리 (다음)
- specs(upload/from-url) · operations · workflows(CRUD+expose) · executions.
- repositories: SQLite CRUD, JSON 컬럼 (de)serialize.
- 검증: 각 엔드포인트 curl 라운드트립, 스펙 업로드→오퍼레이션 생성.

### 4단계 — 프론트엔드
- `templates/base.html`, `editor.html`, `partials/`, `static/style.css`, `static/canvas.js`.
- 디자인: `_design_ref` 시안 1:1, `BUILD_GUIDELINES.md` 합격 기준 전부 통과.
- 검증: 에디터 3분할 레이아웃, 노드 카드 §4 단언, 라이트/다크 토글.

### 5단계 — 캔버스 도구
- 줌, 자동 정렬(dagre/elkjs longest-path), 다중선택, 맞춤/균등분배.

### 6단계 — MCP 노출
- `backend/mcp_server.py`(load_exposed_workflows / resolver / build_input_schema / apply_tool_args), expose 엔드포인트, 에디터 UI, Claude Desktop config.
- 검증: 노출 워크플로우가 MCP 도구로 보이고 호출 시 그래프 실행.

### 7단계 (별도 플랜) — 제어 흐름 노드 + DAG/루프
- 분기/반복/병합 노드, executor 재설계(토폴로지 평가, 미선택 분기 스킵). 노드 타입별 단계 테스트.

## 의존 관계
1 → 2 → 3 → 4 → 5 → 6 → 7. (4·5는 3 이후 병렬 가능, 6은 3 완료 필수)

## 검증 기준 (공통)
- 정확성 → 재현성 → 보안 → 운영 안정성 우선.
- 모든 색 `var(--*)` 토큰, 깨진 `var()` 폴백 없음.
- 시크릿 미영속(인증 토큰은 요청 시점에만 주입).
