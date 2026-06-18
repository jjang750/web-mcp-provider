# MCP Provider

OpenAPI/Swagger 스펙을 올리면 각 API 오퍼레이션을 **노드**로 만들고, 드래그앤드롭 캔버스에서 노드를 엣지로 연결해 **워크플로우**를 구성·실행합니다. 분기·반복 등 제어 흐름 노드로 로직을 짤 수 있고, 완성된 워크플로우는 **MCP 서버로 외부 MCP 클라이언트(Claude Desktop 등)에 도구로 노출**됩니다. 비개발자도 쓸 수 있도록 UI 언어는 한국어입니다.

> 기술 스택: **FastAPI + Jinja2 + Drawflow + SQLite** · 빌드 도구 없음(CDN/정적 자산) · Python 3.10+

---

## 핵심 흐름
스펙 업로드 → 오퍼레이션을 캔버스로 드래그 → 노드 연결·로직 구성 → 실행/검증 → **MCP 도구로 노출**

## 주요 기능
- **메인 화면**(`/`): 워크플로우 카드 목록(노출 상태·메서드·노드 수·수정시각), 생성/복제/삭제, 스펙 업로드(파일·URL), 검색, 라이트/다크 테마, **실행 로그(Audit) 링크**.
- **에디터**(`/editor/{id}`): Drawflow 캔버스, 오퍼레이션 팔레트(클릭/드래그로 노드 추가), 노드 속성·엣지 데이터 매핑 편집, 자동정렬·맞춤·균등분배(다중 선택), 줌, 이름·설명 편집.
  - **리턴값 미리보기**: API 노드 선택 시 응답 스키마의 `$ref`를 풀어 JSONPath 필드·예시를 표시. 필드 클릭 시 경로 복사(비보안 컨텍스트 폴백 포함).
- **제어 흐름 노드(로직 팔레트)**:
  - **분기(IF)**: 조건 평가 → true/false 포트로 분기. 미선택 분기의 하류는 스킵.
  - **스위치(Switch)**: 좌변 값별 다중 분기(케이스 **최대 10** + default 포트).
  - **병합(Merge)**: 여러 상류 흐름을 합류.
  - **필터(Filter)**: 조건 미충족 시 이후 노드 실행 차단.
  - **변환(Set)**: 상류 응답에서 JSONPath로 필드 추출/고정값으로 출력 객체 재구성.
- **조건 평가**: 연산자 `== != > < >= <= contains exists truthy falsy`. 우변 **타입 지정**(auto/string/number/boolean/null) — auto는 불리언↔"true" 등 관용 비교.
- **실행/로그**: 폼/JSON 입력 + 인증(Bearer/API Key). **진입 노드만 입력**받고, 하류 노드는 상류 OUTPUT에서 같은 이름 값을 **자동 주입**(명시 매핑·정적값 우선). 노드별 상태색·노드명·평가결과·INPUT/OUTPUT 표시, hover 복사. 결과는 종료 노드에서 노드ID 래핑 없이 반환.
- **MCP 노출**: 노출 토글 → `backend/mcp_server.py`(stdio)가 워크플로우를 MCP 도구로 제공. 성공 시 최종 결과(final)만 깔끔히 반환.
- **감사 로그**(`/logs`): 웹 실행·MCP 호출 이력(출처·도구명·시간·상태), 출처 필터(전체/웹/MCP), 실행별 노드 로그 상세.

## 프로젝트 구조
```
app/
  backend/
    app.py                FastAPI 앱(lifespan→init_db, 라우터/정적/템플릿 마운트, /, /logs, /editor)
    db.py                 SQLite 연결 + 멱등 스키마 + 컬럼 마이그레이션
    models.py             Pydantic 와이어 모델
    engine_bridge.py      engine 호출 래퍼(지연 import)
    mcp_server.py         MCP 서버(stdio) — 노출 워크플로우를 도구로, 호출 시 감사 로그 저장
    routers/              specs · operations · workflows · executions
    repositories/         specs · workflows · executions (SQLite CRUD)
  engine/                 순수 모듈(FastAPI 비의존)
    parser.py             OpenAPI v2/v3 → 오퍼레이션 추출
    http_client.py        httpx 래퍼(base_url 우선순위·프로토콜 가드·인증)
    executor.py           그래프 검증/토폴로지/순차 실행 + 제어흐름(IF/Switch/Merge/Filter/변환)·자동 주입·노드 로그
    schema_fields.py      응답 스키마 $ref 평탄화(리턴값 미리보기)
  templates/              index.html · editor.html · logs.html
  static/                 tokens.css · style.css · canvas.js · vendor/(drawflow)
  tools/dummy_api.py      테스트용 더미 API(:8000)
  tests/                  pytest (parser·http_client·executor·schema_fields·API 통합)
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
- 브라우저에서 `http://localhost:9000/` 접속. 사내 공유 시 `http://<서버IP>:9000/` 도 가능(클립보드는 execCommand 폴백으로 동작).
- 워크플로우가 호출할 대상 API가 필요합니다. 테스트용 더미 API:
  ```bash
  PYTHONPATH=. uvicorn tools.dummy_api:app --port 8000
  ```
- 더미 API(:8000) ↔ provider(:9000) 포트 구분. 스펙에 `servers`가 없으면 `MCP_DEFAULT_BASE_URL`(기본 `http://localhost:8000`)로 폴백.

## 테스트
```bash
cd app
PYTHONPATH=. python -m pytest tests -q     # 41 passed
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
> 감사 로그(`/logs`)에서 MCP 호출이 보이려면 **MCP 서버와 웹앱이 같은 DB**(`MCP_DB_PATH` 또는 기본 `app/mcp_provider.db`)를 사용해야 합니다.

## MCP Inspector로 점검 (v0.22.0)
stdio MCP 서버의 도구 목록·호출을 GUI로 점검하는 공식 도구입니다. **Node.js 18+** 필요.

PowerShell(앱 디렉터리 `app/`, venv 활성화 상태):
```powershell
$env:PYTHONPATH="."
$env:MCP_GROUP="xperp"                                  # 선택(특정 그룹만)
$env:MCP_DB_PATH="C:\...\web-mcp-provider\app\mcp_provider.db"   # 웹앱과 동일하게(감사 로그 공유)
npx @modelcontextprotocol/inspector .\.venv\Scripts\python.exe -m backend.mcp_server
```
macOS/Linux:
```bash
PYTHONPATH=. MCP_GROUP=xperp npx @modelcontextprotocol/inspector .venv/bin/python -m backend.mcp_server
```
- 실행하면 콘솔에 접속 URL이 출력됩니다(기본 UI `http://localhost:6274`, 프록시 `6277`). 보안 토큰이 포함된 URL을 그대로 브라우저에서 엽니다.
- 좌측에서 **Connect** → **Tools** 탭 → `List Tools`로 노출된 도구 확인 → 인자 입력 후 `Run`으로 호출.
- 도구가 안 보이면: 워크플로우 **MCP 노출 ON** 여부, `MCP_GROUP` 일치, `pip install mcp` 설치 확인. 노출/그래프 변경 후에는 Inspector를 **재연결**(서버 재기동).
- Inspector로 호출한 것도 `/logs`에 `source=mcp`로 기록됩니다(웹앱과 같은 `MCP_DB_PATH`일 때).

## 환경 변수
| 변수 | 기본값 | 설명 |
|---|---|---|
| `MCP_DB_PATH` | `app/mcp_provider.db` | SQLite 파일 경로(provider·MCP 서버가 동일 DB를 봐야 감사 로그 공유) |
| `MCP_DEFAULT_BASE_URL` | `http://localhost:8000` | 노드/오퍼레이션에 base_url이 없을 때 폴백 |
| `MCP_HTTP_TRUST_ENV` | `0` | 1이면 엔진 HTTP 호출에 시스템 프록시(env) 사용 |
| `MCP_GROUP` / `MCP_SERVER_NAME` | (없음) | MCP 서버 그룹 필터 / 서버 이름 |

## 최근 변경 (7단계 — 제어 흐름 & 운영)
- 제어 흐름 노드 추가: **분기(IF)·스위치(Switch, 최대 10케이스)·병합(Merge)·필터(Filter)·변환(Set)**.
- 조건 평가 개선: 불리언↔문자열 관용 비교, **우변 타입 지정**(auto/string/number/boolean/null).
- 실행 UX: **진입 노드만 입력**, 하류 노드는 상류 OUTPUT에서 동명 값 **자동 주입**. 실행창에 자동 주입 항목 표시.
- 종료/결과: 노드ID 래핑 제거(단일 상류 통과)·동일 상류 중복 제거, `final` 결과 + MCP는 최종값만 반환.
- 실행 로그: 노드명·평가결과 표시, INPUT/OUTPUT hover 복사(비보안 컨텍스트 폴백).
- 리턴값 미리보기: 응답 스키마 `$ref` 평탄화(JSONPath 목록·예시).
- **감사 로그(`/logs`)**: 웹/MCP 실행 이력(출처·도구명) + 필터.

## 참고 / 주의
- 외부 라이브러리(Drawflow)는 CDN 대신 `static/vendor/`에 로컬 포함(사내망 대비).
- `templates/editor.html`·`index.html`은 CSS/JS를 인라인합니다 — 화면 동작 변경 시 `static/`만 고치면 반영되지 않으니 해당 템플릿을 수정하세요.
- 클립보드 복사는 보안 컨텍스트(HTTPS/localhost)에서 표준 API, 그 외(IP/HTTP)에서는 `execCommand` 폴백 사용.
- 진행 상황·이슈는 `app/HANDOFF.md`, 단계 플랜은 `app/PLAN_STAGE7.md` 참고.

## 라이선스
사내 프로젝트(미정).
