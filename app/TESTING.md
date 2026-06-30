# 테스트 방법 (1~3단계)

> 위치: `web-mcp-provider/app/`. Windows 기준 명령(PowerShell). venv 권장.

## 0. 준비 (최초 1회)
```powershell
cd C:\Users\PC-727\Documents\Claude\Projects\web-mcp-provider\app
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```
- 중요: `jinja2>=3.1` 필수(구버전이면 화면이 500). requirements.txt 가 처리함.

## 1. 자동 테스트 (가장 빠른 검증)
```powershell
$env:PYTHONPATH="."
pytest tests -q
```
기대: **20 passed** (엔진 단위 18 + API 통합 2).
- 엔진: parser(v2/v3·base_url·서버변수), http_client(우선순위·프로토콜가드·인증), executor(JSONPath·사이클거부·순차실행·실패스킵).
- API: 스펙업로드→오퍼레이션→워크플로우→실행→조회→노출→삭제 라운드트립, 실패 시 하류 스킵 영속.

## 2. 수동 End-to-End (실제 HTTP 호출 확인)
터미널 **2개**가 필요합니다.

### 터미널 A — 더미 API 서버(:8000)
> 더미 API 는 `app/`과 분리된 독립 프로젝트(`web-mcp-provider/tools/`). app 의 venv/PYTHONPATH 불필요.
```powershell
# 로컬 실행
cd ..\tools          # web-mcp-provider\tools
pip install -r requirements.txt
uvicorn dummy_api:app --host 0.0.0.0 --port 8000

# 또는 Docker 실행
cd ..\tools
docker build -t dummy-api .
docker run --rm -p 8000:8000 dummy-api
```
확인: 브라우저로 http://localhost:8000/docs , 스펙은 http://localhost:8000/openapi.json

### 터미널 B — Provider 앱(:9000)
```powershell
cd ...\app; .\.venv\Scripts\Activate.ps1; $env:PYTHONPATH="."
uvicorn backend.app:app --port 9000
```
확인:
- http://localhost:9000/healthz → `{"status":"ok","tables":[...7개]}`
- http://localhost:9000/docs → 모든 API 가 보임(Swagger UI)
- http://localhost:9000/ , http://localhost:9000/editor/1 → 화면 로드(에디터 UI 는 4단계에서 구현)

### 터미널 B 에서 흐름 실행 (curl)
```powershell
# 1) dummy 스펙을 URL로 등록
curl -s -X POST http://localhost:9000/api/specs/from-url -H "Content-Type: application/json" -d '{\"url\":\"http://localhost:8000/openapi.json\",\"name\":\"dummy\"}'
# → operation_count: 3

# 2) 오퍼레이션 확인 (getUser 의 id 확인)
curl -s http://localhost:9000/api/specs/1/operations

# 3) 워크플로우 생성
curl -s -X POST http://localhost:9000/api/workflows -H "Content-Type: application/json" -d '{\"name\":\"사용자조회\"}'

# 4) 그래프 저장 (start → getUser, user_id=1). operation_id 는 2)에서 확인한 값(보통 1)
curl -s -X PUT http://localhost:9000/api/workflows/1 -H "Content-Type: application/json" -d '{\"nodes\":[{\"id\":\"start\",\"type\":\"start\"},{\"id\":\"n1\",\"type\":\"api_call\",\"operation_id\":1,\"params\":{\"path\":{\"user_id\":1}}}],\"edges\":[{\"id\":\"e0\",\"source\":\"start\",\"target\":\"n1\"}]}'

# 5) 실행
curl -s -X POST http://localhost:9000/api/workflows/1/run -H "Content-Type: application/json" -d '{\"initial_input\":{}}'
```
기대 결과(5번): `status: success`, n1 output =
```json
{"id":1,"name":"김철일","email":"chungil@example.com"}
```
실행 결과 재조회: `curl http://localhost:9000/api/executions/1`

### 실패 케이스 확인
4번에서 `user_id` 를 빼거나 없는 경로를 쓰면 → 해당 노드 `failed`, 하류 노드 `skipped`, 전체 `failed`(앱은 죽지 않음).

## 2-1. 더미 API (XpERP 입주자 관리) 테스트
더미 API(:8000)는 STT 통화분석 설계 기반 XpERP 입주자 관리 API. 9개 그룹 20개 엔드포인트. 터미널 A 가 떠 있는 상태에서 확인.
공통 필수: `aptcd`(6자리, 예 `001023`), 조회년월 `yearmon`(YYYYMM). 시드 단지 `001023`. 인메모리 → 재기동 시 리셋.

### 가장 빠른 확인 — /docs 클릭 테스트
http://localhost:8000/docs 에서 그룹별(IMPO/RECP/INSP/OCCP/CMPL/ACCT/HR/PARK) "Try it out". 한글값은 Swagger UI 가 자동 인코딩.

### curl (조회)
```bash
curl "http://localhost:8000/impo/detail?aptcd=001023&yearmon=202510&dong=101&ho=305"
curl "http://localhost:8000/recp/unpaid/list?aptcd=001023&yearmon=202510&months=3"
curl "http://localhost:8000/occp/unit?aptcd=001023&dong=101&ho=305"
# 한글 쿼리값은 -G --data-urlencode 로 인코딩
curl -G "http://localhost:8000/insp/status" --data-urlencode "aptcd=001023" --data-urlencode "yearmon=202510" --data-urlencode "type=수도"
```

### curl (입주자 OCCP 쓰기 — 등록→전출처리→삭제)
```bash
curl -X POST  http://localhost:8000/occp/unit -H "Content-Type: application/json" -d '{"aptcd":"001023","dong":"102","ho":"303","name":"신규입주","members":2}'
curl -X PATCH "http://localhost:8000/occp/unit?aptcd=001023&dong=102&ho=303" -H "Content-Type: application/json" -d '{"status":"전출","moveout":"2025-12-31"}'
curl -X DELETE "http://localhost:8000/occp/unit?aptcd=001023&dong=102&ho=303"
```
기대: POST→`status:created`, PATCH→`status:patched`+`changed`, DELETE→`status:deleted`. 잘못된 aptcd 400 / 없는 세대 404 / 필수 누락 422.

### Provider(:9000) 워크플로우로 묶어 테스트
1. 스펙 재등록: `POST /api/specs/from-url` body `{"url":"http://localhost:8000/openapi.json","name":"xperp"}` → 20개 오퍼레이션 등록.
2. `/editor/{id}` 에서 IMPO/RECP/INSP 등 오퍼레이션을 노드로 추가 → 저장 → 실행. 시드 워크플로우 경로(`/impo/detail`·`/recp/status`·`/insp/status`)와 일치.

## 3. /docs 로 클릭 테스트 (curl 없이)
http://localhost:9000/docs 에서 각 엔드포인트를 "Try it out" 으로 직접 실행할 수 있습니다.

## 참고
- 더미서버 :8000 ↔ provider :9000 포트 구분(사양서 §10).
- 사내 프록시 환경이면 외부 스펙 fetch 시 `setx MCP_HTTP_TRUST_ENV 1` 로 프록시 사용을 켤 수 있음(기본은 무시).
- DB 파일 위치 변경: 환경변수 `MCP_DB_PATH`.
