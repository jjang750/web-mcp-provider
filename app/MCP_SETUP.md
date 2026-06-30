# 6단계 — MCP 노출 + Claude Desktop 연동

워크플로우를 **MCP 도구**로 외부 클라이언트(Claude Desktop 등)에 노출합니다.

## 1. 워크플로우 노출(에디터에서)
1. `/editor/{id}` 에서 워크플로우 구성 → **저장**.
2. 상단 2번째 툴바에서 **도구 이름**(영문 권장, 예 `get_impo_detail`)·**MCP 그룹**(예 `xperp`) 입력 → **MCP 노출 토글 ON**.
   - 도구 이름 비우면 자동으로 `workflow_{id}_{slug}` 생성(한글 이름은 description 으로만 노출).
3. 시작 노드에 연결된 API 노드의 **미충족 필수 파라미터**가 도구 입력 스키마가 됩니다.
   (정적값으로 채워두면 입력에서 빠지고, 비워두면 호출 시 입력받음)

## 2. 의존성(가상환경에 MCP SDK)
```powershell
cd C:\Users\PC-727\Documents\Claude\Projects\web-mcp-provider\app
.\.venv\Scripts\Activate.ps1
pip install mcp
```

## 3. MCP 서버 단독 점검(선택)
```powershell
$env:PYTHONPATH="."; $env:MCP_GROUP="xperp"
python -m backend.mcp_server   # stdio 대기 → Ctrl+C
```
(에러 없이 대기하면 정상. 실제 도구 목록은 Claude Desktop 이 붙을 때 노출됩니다.)

## 4. Claude Desktop 설정
설정 파일: `%APPDATA%\Claude\claude_desktop_config.json` (없으면 생성)

```json
{
  "mcpServers": {
    "xperp": {
      "command": "C:\\Users\\PC-727\\Documents\\Claude\\Projects\\web-mcp-provider\\app\\.venv\\Scripts\\python.exe",
      "args": ["-m", "backend.mcp_server"],
      "cwd": "C:\\Users\\PC-727\\Documents\\Claude\\Projects\\web-mcp-provider\\app",
      "env": {
        "PYTHONPATH": "C:\\Users\\PC-727\\Documents\\Claude\\Projects\\web-mcp-provider\\app",
        "MCP_GROUP": "xperp",
        "MCP_DEFAULT_BASE_URL": "http://localhost:8000"
      }
    }
  }
}
```
- `MCP_GROUP` 생략 시 노출된 모든 워크플로우가 도구로 나옵니다. 그룹별로 분리하려면 그룹마다 항목 추가.
- 워크플로우가 실제 API 를 호출하므로, 대상 API(여기선 더미 :8000)가 떠 있어야 실행이 성공합니다. base_url 이 스펙에 없으면 `MCP_DEFAULT_BASE_URL` 로 폴백.
- **DB 공유 주의:** provider 앱과 동일한 SQLite 를 봐야 합니다. provider 를 `MCP_DEFAULT`(기본 `app/mcp_provider.db`)로 띄웠다면 그대로 두면 되고, `MCP_DB_PATH` 를 커스텀했다면 위 env 에도 `MCP_DB_PATH` 를 동일하게 추가하세요.

## 5. 적용 / 주의
- Claude Desktop **완전 종료 후 재시작** → 도구 목록 로드.
- **도구 목록은 MCP 서버 기동 시 1회 생성**됩니다. 노출/그룹/도구이름/그래프를 바꾸면 **Claude Desktop 을 재시작**해야 반영됩니다.
- 도구명은 영문/숫자/`_`/`-` 만 유효(한글 이름은 자동 fallback). 한글 설명은 description 으로 표시됩니다.

## 6. 동작 방식(요약)
`load_exposed_workflows()`(그룹 필터) → 워크플로우별 `build_tool_name` + `build_input_schema`(미충족 필수 파라미터) → 도구 등록.
도구 호출 시 `apply_tool_args` 로 인자를 그래프 노드 params 에 주입 → 엔진(`run_workflow`)으로 순차 실행 → 결과(JSON) 반환.
