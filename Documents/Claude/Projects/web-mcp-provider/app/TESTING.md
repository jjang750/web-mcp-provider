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
```powershell
cd ...\app; .\.venv\Scripts\Activate.ps1; $env:PYTHONPATH="."
uvicorn tools.dummy_api:app --port 8000
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

## 3. /docs 로 클릭 테스트 (curl 없이)
http://localhost:9000/docs 에서 각 엔드포인트를 "Try it out" 으로 직접 실행할 수 있습니다.

## 참고
- 더미서버 :8000 ↔ provider :9000 포트 구분(사양서 §10).
- 사내 프록시 환경이면 외부 스펙 fetch 시 `setx MCP_HTTP_TRUST_ENV 1` 로 프록시 사용을 켤 수 있음(기본은 무시).
- DB 파일 위치 변경: 환경변수 `MCP_DB_PATH`.
