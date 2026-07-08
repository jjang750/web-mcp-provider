# HANDOFF — 파라미터 입력 모드(고정/입력) + LangGraph용 평면 인자 이름

작성일: 2026-07-01 · 대상: web-mcp-provider (app)

## 0. 목표

**LangGraph → MCP provider** 호출. LangGraph(LLM)가 `aptcd`, `dong`, `ho` 같은
자연스러운 파라미터를 직접 만들어 MCP 도구를 호출할 수 있어야 한다.
→ 도구 inputSchema 는 **평면(flat) 인자 이름**을 노출하고(내부적으로 노드 파라미터에 매핑),
   어떤 파라미터를 인자로 받을지는 **고정/입력** 토글로 명시한다.

## 1. 배경 / 문제

MCP 도구 입력 스키마(`build_input_schema`)는 **"노드 파라미터에 값이 있으면 = 정적값 = 입력에서 제외"** 로 추론했다.
이 때문에 워크플로우 캔버스에서 테스트값을 입력·저장하면 그 값이 영구 정적값이 되어, MCP 도구에서 해당 파라미터가 사라지고 호출 시 입력이 무시되는 문제가 발생했다(예: WF8 `get_resident_uesr` 가 `dry_run` 만 노출).

## 2. 해결 — n8n 식 명시적 모드

파라미터마다 **고정(fixed) / 입력(input)** 을 명시적으로 구분한다(n8n 의 fixed↔expression 분리와 동일 개념). 추론이 아니라 사용자의 명시적 의도로 노출 여부를 결정한다.

- **고정**: 값을 항상 사용, MCP 입력에서 숨김.
- **입력**: MCP 도구 인자로 노출. 값이 있으면 그 값을 `default` 로 제공.
- **상류 출력 주입**: 기존 **엣지 데이터 매핑**(`data_mapping`) 그대로 사용(= n8n expression). → 제거하지 않음(아래 4 참고).

저장 형식: 노드 `params` 안에 예약 키 `_input` 추가. `loc.name` 문자열 배열.

```json
"params": {
  "query": { "aptcd": "001023", "dong": "101", "ho": "305" },
  "_input": ["query.aptcd", "query.dong", "query.ho"]
}
```

`_input` 은 `params` 최상위 키이며 executor 는 `path/query/header/body` 만 읽으므로 실행에 영향 없음. DB(`nodes.params` JSON) 라운드트립으로 마이그레이션 없이 영속.

## 2-1. 평면 인자 이름 + 별칭 (LangGraph 친화)

도구 inputSchema 의 property 이름은 **노드 스코프 키(`3.query.aptcd`)가 아니라 파라미터명 그대로**(`aptcd`, `dong`, `ho`)로 노출한다. 이유: LLM/LangGraph 의 function-calling 인자 이름은 점(`.`)·숫자 시작을 싫어하고, 자연스러운 이름이라야 모델이 올바르게 채운다.

- 같은 파라미터명이 여러 노드/위치에 있으면 `<nid>_<loc>_<pname>` 로 자동 구분.
- 내부 **별칭 맵** `alias[노출키] = "<nid>.<loc>.<pname>"` 을 도구별로 보관.
- `call_tool` 이 들어온 평면 인자를 별칭으로 되돌려 실제 노드 파라미터에 주입. 별칭에 없는 키는 그대로 통과(노드 스코프 키 직접 전달도 계속 허용).

예: 도구가 `{aptcd, dong, ho}` 를 노출 → LLM 이 `{aptcd:"001023", dong:"101"}` 호출 → 내부적으로 `3.query.aptcd=001023`, `3.query.dong=101` 주입.

## 3. 변경 파일

- `backend/mcp_server.py`
  - `_collect_input_params()`: 노출 후보(진입 노드, `_input`/정적/매핑 규칙, default·required) 수집.
  - `build_schema_and_alias()`: 평면 이름 JSON Schema + 별칭 맵 생성(이름 충돌 시 노드로 구분).
  - `build_input_schema()`: 위 함수의 스키마만 반환(하위호환 래퍼).
  - `build_tools()`: 도구에 `alias` 저장. `call_tool()`: 평면 인자 → 별칭 해석 후 주입.
  - `_input` 표시 파라미터는 정적값·엣지매핑이 있어도 노출하고 정적값을 `default` 로 부여. 기본값 있으면 `required` 제외. **`_input` 미사용 시 기존 동작 유지(하위호환).**
- `static/canvas.js` · `showProps()` api 분기
  - raw params JSON 텍스트박스 → 파라미터별 `[값 + 고정/입력 토글]` 구조 에디터로 교체.
  - 적용 시 `params` 와 `params._input` 구성. `<details>` 안에 **고급: params JSON 직접 편집** 폴백 유지.
- `tests/test_mcp_schema.py` · 평면 이름/별칭/충돌/`_input`/default/하위호환 테스트.

## 4. "노드 속성의 입력 매핑을 빼야 하나?" → 권장: 유지(역할 분리)

세 가지는 **서로 다른 값 소스**이며 모두 필요하다.

| 소스 | 의미 | UI |
|---|---|---|
| 고정 | 항상 같은 값 | 노드 속성 토글=고정 |
| 입력 | MCP 인자로 받음 | 노드 속성 토글=입력 |
| 매핑 | 상류 노드 출력에서 주입 | 엣지 데이터 매핑 |

엣지 매핑은 단일 노드 속성이 아니라 **두 노드 간 연결**의 속성이므로 노드 속성에서 빼는 것이 맞다(현재도 엣지 클릭 시 표시). 따라서 "노드 속성의 입력 매핑"이라는 혼동 지점을 없애려면, 노드 속성에는 고정/입력만 두고 상류 주입은 엣지에서만 다루도록 위치를 명확히 분리하는 것을 권장한다(기능 제거가 아니라 위치 정리).

향후 개선(선택): 파라미터 행에 소스 셀렉터 `[고정 | 입력 | 매핑]` 를 두고, 매핑 선택 시 해당 엣지 `data_mapping` 을 같이 편집하도록 통합 → n8n 의 단일 필드 모델에 가장 근접.

## 5. 테스트 (콘솔)

WF8 은 정적값을 비워둔 상태라 이미 aptcd/dong/ho 가 입력으로 노출된다.

```powershell
cd C:\Users\PC-727\workspace\xperp_qna_chatbot
venv\Scripts\python scripts\test_mcp_connect.py --group resident `
  --call get_resident_uesr --aptcd 001023 --dong 101 --ho 305
```

기대: 스키마가 **평면 키 `aptcd / dong / ho`** 를 노출(더 이상 `매칭 키 없음` 경고 없음), 넘긴 값이 결과에 반영. `aptcd` 는 required.

LangGraph(langchain-mcp-adapters 등)에서는 도구 인자 스키마가 `{aptcd, dong, ho}` 로 보이므로 모델이 그대로 채워 호출하면 된다.

정식 검증(mcp 설치 환경):

```bash
python -m pytest tests/test_mcp_schema.py -q
```

> 주의: 이 세션의 리눅스 샌드박스는 마운트 읽기 캐시 truncate 이슈로 방금 편집한 파일을
> 온전히 못 읽어 pytest 를 직접 실행하지 못했다. 대신 동일 로직을 독립 스크립트로 옮겨
> 전 케이스(평면 이름/별칭/roundtrip/default override/충돌) + 실 WF8 스키마 산출을 검증 완료.
> 실제 pytest 는 Windows 개발 환경에서 위 명령으로 확인 권장.

## 6. 테스트 (URL / 에디터)

1. `/editor/8` 접속 → API 노드 클릭 → 속성 패널에서 각 파라미터의 **고정/입력** 토글 확인.
2. aptcd 를 `001023` 입력 후 토글을 **입력** 으로 → 적용 → 저장.
3. MCP 재조회(또는 `test_mcp_connect.py` 재실행)에서 평면 인자 `aptcd` 의 `default=001023` 확인.

## 7. 주의 / 후속

- 노드 params 만 바꾸고 워크플로우를 저장하지 않으면 `workflows.updated_at` 이 안 바뀌어, **상시 실행 중인 MCP 서버**는 변경을 감지 못 할 수 있다 → 에디터에서 한 번 저장하면 `updated_at` 갱신 + `tools/list_changed` 알림.
- 마운트 쓰기 캐시 truncate 이슈로 DB/파일은 로컬(/tmp) 수정 후 복사하는 패턴 사용.
- DB 백업: `mcp_provider.db.bak_20260630_233448`.
