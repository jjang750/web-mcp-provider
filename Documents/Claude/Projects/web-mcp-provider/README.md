# MCP Provider

OpenAPI/Swagger 스펙을 올리면 각 API 오퍼레이션을 **노드**로 만들고, 드래그앤드롭 캔버스에서 노드를 엣지로 연결해 **순차 실행 워크플로우**를 구성·실행합니다. 완성된 워크플로우는 **MCP 서버로 외부 MCP 클라이언트(Claude Desktop 등)에 도구로 노출**됩니다. 비개발자도 쓸 수 있도록 UI 언어는 한국어입니다.

> 기술 스택: **FastAPI + Jinja2 + Drawflow + SQLite** · 빌드 도구 없음(CDN/정적 자산) · Python 3.10+

---

## 핵심 흐름
스펙 업로드 → 오퍼레이션을 캔버스로 드래그 → 노드 연결·파라미터 설정 → 실행/검증 → **MCP 도구로 노출**

## 주요 기능
- **메인 화면**(`/`): 워크플로우 카드 목록(노출 상태·메서드·노드 수·수정시각), 생성/복제/삭제, 스펙 업로드(파일·URL), 검색, 라이트/다크 테마.
- **에디터**(`/editor/{id}`): Drawflow 캔버스, 좌측 오퍼레이션 팔레트(클릭/드래그로 노드 추가), 노드 속성(Base URL·params)·엣지 데이터 매핑 편집, 자동정렬·맞춤·균등분배(다중 선택 지원), 줌, 이름·설명 편집 모달.
- **실행/로그**: 폼/JSON 입력 + 인증(Bearer/API Key)으로 실행, 노드별 상태색·입력/출력 상세 로그(DB 영속).
- **MCP 노출**: 노출 토글 → `backend/mcp_server.py`(stdio)가 워크플로우를 MCP 도구로 제공. 시작 노드에 연결된 API 노드의 미충족 필수 파라미터가 도구 입력 스키마가 됨.

## 프로젝트 구조
```
app/
  backend/
    app.py                FastAPI 앱(lifespan→init_db, 라우터/정적/템플릿 마운트)
    db.py                 SQLite 연결 + 멱등 스키마 + 컬럼 마이그레이션
    models.py             Pydantic 와이어 모델
    engine_bridge.py      engine 호출 래퍼(지연 import)
    mcp_server.py          MCP 서버(stdio) — 노출 워크플로우를 도구로
    routers/              specs · operations · workflows · executions
    repositories/         specs · workflows · executions (SQLite CRUD)
  engine/                 순수 모듈(FastAPI 비의존)
    parser.py             OpenAPI v2/v3 → 오퍼레이션 추출
    http_client.py        httpx 래퍼(base_url 우선순위·프로토콜 가드·인증)
    executor.py           그래프 검증/토폴로지/순차 실행/노드 로그
  templates/              base.html · index.html · editor.html
  static/                 tokens.css · style.css · canvas.js · vendor/(drawflow)
  tools/dummy_api.py      테스트용 더미 API(:8000)
  tests/                  pytest (parser·http_client·executor·API 통합)
  mcp_provider.db         SQLite 단일 파일(런타임 생성, git 제외)
```

## 설치 & 실행
```bash
cd app
python -m venv .venv
# Windows:  .\.venv\Scripts\Activate.ps1   |  macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt

# 앱 기동 (provider = :9000)
set PYTHONPATH=.        # PowerShell: $env:PYTHONPATH="."   |  bash: export PYTHONPATH=.
uvicorn backend.app:app --port 9000
```
- 브라우저에서 `http://localhost:9000/` 접속.
- 워크플로우가 호출할 대상 API가 필요합니다. 테스트용 더미 API:
  ```bash
  PYTHONPATH=. uvicorn tools.dummy_api:app --port 8000
  ```
- 더미 API(:8000) ↔ provider(:9000) 포트 구분. 스펙에 `servers`가 없으면 `MCP_DEFAULT_BASE_URL`(기본 `http://localhost:8000`)로 폴백.

## 테스트
```bash
cd app
PYTHONPATH=. python -m pytest tests -q     # 20 passed
```
UI/엔드투엔드 절차는 `app/TESTING.md`, `app/xperp_test_payloads.md` 참고.

## MCP 노출 (Claude Desktop 연동)
1. 에디터에서 워크플로우 저장 → 도구 이름·MCP 그룹 입력 → **MCP 노출 토글 ON**.
2. venv에 `pip install mcp`.
3. `claude_desktop_config.json`에 stdio 서버 등록(상세: `app/MCP_SETUP.md`):
```json
{
  "mcpServers": {
    "xperp": {
      "command": "<venv>/python",
      "args": ["-m", "backend.mcp_server"],
      "cwd": "<repo>/app",
      "env": { "PYTHONPATH": "<repo>/app", "MCP_GROUP": "xperp", "MCP_DEFAULT_BASE_URL": "http://localhost:8000" }
    }
  }
}
```
> 도구 목록은 서버 기동 시 1회 생성 → 노출/그룹/이름/그래프 변경 후 **MCP 클라이언트 재시작** 필요. `MCP_GROUP` 생략 시 노출된 전체 워크플로우 노출.

## 환경 변수
| 변수 | 기본값 | 설명 |
|---|---|---|
| `MCP_DB_PATH` | `app/mcp_provider.db` | SQLite 파일 경로(provider·MCP 서버가 동일 DB를 봐야 함) |
| `MCP_DEFAULT_BASE_URL` | `http://localhost:8000` | 노드/오퍼레이션에 base_url이 없을 때 폴백 |
| `MCP_HTTP_TRUST_ENV` | `0` | 1이면 엔진 HTTP 호출에 시스템 프록시(env) 사용 |
| `MCP_GROUP` / `MCP_SERVER_NAME` | (없음) | MCP 서버 그룹 필터 / 서버 이름 |

## 참고 / 주의
- 외부 라이브러리(Drawflow)는 CDN 대신 `static/vendor/`에 로컬 포함(사내망 대비).
- 디자인 기준: `app/_design_ref/`(BUILD_GUIDELINES, 디자인 시스템 standalone) — 토큰은 `static/tokens.css`만 사용(하드코딩 hex 금지).
- 진행 상황·이슈는 `app/HANDOFF.md` 참고.

## 라이선스
사내 프로젝트(미정).
