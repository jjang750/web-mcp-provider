# 7단계 플랜 — 제어 흐름 노드 (IF 분기 최소 구현)

> 작성: 2026-06-17 · 범위: **조건 분기(IF) 노드만** (Loop/Switch/Merge UI는 후속)
> 결정 근거: 현재 executor 는 Kahn 토폴로지 1패스 실행. 분기는 이 모델에 얹을 수 있으나
> 반복(Loop)은 사이클이라 엔진 재설계가 필요 → 분리.

## 설계 요약
- **노드 타입 추가**: `condition` (입력 1, 출력 2 — true/false 포트).
- **엣지 라벨**: condition 노드의 나가는 엣지에 `label`("true"/"false") 부여.
  - 프론트는 Drawflow 출력 포트(output_1=true, output_2=false)에서 라벨을 유도.
  - 백엔드는 `edges.label` 컬럼에 영속(executor 가 분기 판단에 사용).
- **조건 설정**: 노드 `params.condition = {left, op, right}`.
  - `left`: 상류 출력에 대한 JSONPath(예: `$.status`).
  - `op`: `==,!=,>,<,>=,<=,contains,exists,truthy,falsy`.
  - `right`: 비교 리터럴(exists/truthy/falsy 는 미사용).
- **실행 규칙**:
  1. condition 노드 입력 = 첫 상류 노드 출력(없으면 initial_input).
  2. 조건 평가 → branch = "true"/"false".
  3. condition 출력 = 상류 출력 그대로 통과(pass-through) → 하류 매핑 유지.
  4. **미선택 분기의 배타적 하류 노드만 skipped** (선택 분기에서도 도달 가능한 노드는 살림 → Merge 재합류 지원).
  5. 조건 평가 실패 → 노드 failed, 전체 하류 skipped(기존 실패 규칙과 동일).

## 작업 순서
1. (문서) 본 플랜.
2. models.py: `NodeType += condition`, `Edge.label`.
3. db.py: edges 스키마/마이그레이션 `label TEXT`.
4. repositories/workflows.py: edge (de)serialize 에 label.
5. engine/executor.py: condition 처리 + `_eval_condition`/`_outgoing_edges`/`_descendants_incl`.
6. tests: true/false/스킵/재합류 + 회귀.
7. front: canvas.js(팔레트 클릭·노드 렌더·속성 편집·export/load), editor.html/style.css.
8. 검증: pytest, node --check, 앱 기동/렌더. 사용자 콘솔/URL 테스트 절차 제공.

## 테스트(사용자 제공)
- 콘솔: `pytest tests -q`.
- URL: `/editor/{id}` 에서 분기 노드 추가 → start→condition→(true)api / (false)end 구성 →
  initial_input 으로 분기 확인, 실행 로그에서 스킵 경로 확인.

## 비범위(후속)
- Switch/Filter/Loop, Merge 정식 노드, MCP 입력 스키마의 분기 인지.

---
## 7단계(2차) — Switch / Merge / Filter (Loop·Batch 제외)
### 노드 타입(추가)
- `switch` (입력1 · 출력 N=케이스수+1, **케이스 최대 10**). 마지막 출력=default.
- `merge` (입력1[다중 연결] · 출력1).
- `filter` (입력1 · 출력1).

### 엣지 라벨
- switch: 출력 포트 i → `cases[i-1]` 값, 마지막 포트 → `"__default__"`.
- merge/filter: 라벨 없음.

### 실행 규칙(executor)
- **switch**: subject=첫 상류 출력. `value=get_by_path(subject,left)`.
  - `str(value)`가 케이스값과 일치하는 엣지 채택, 없으면 `__default__` 엣지 채택.
  - 라벨 없는 엣지는 항상 통과. 미채택(라벨 있으나 불일치) 분기의 배타적 하류만 skip.
  - 출력=subject(통과). 로그 output={"switch":str(value),"matched":label}.
- **merge**: 출력 = {상류노드id: 출력} (스킵되지 않아 출력이 있는 상류만). 항상 success.
- **filter**: subject=첫 상류 출력. 조건 평가.
  - 참 → 출력=subject(통과), success.
  - 거짓 → success 지만 **전체 하류 skip**(걸러짐). 출력=None.
  - 평가 오류 → failed + 하류 skip.

### 프론트
- 로직 팔레트: 분기(IF)/스위치/병합/필터(루프 제외). 클릭·드래그 추가.
- switch 속성: left + 케이스 목록(추가/삭제, 최대 10) → 적용 시 출력 포트 수 동기(addNodeOutput/removeNodeOutput)+포트 라벨 갱신.
- filter 속성: left/op/right(조건 재사용). merge 속성: 안내.
- exportGraph: switch 라벨(포트→케이스/__default__). loadWorkflow: switch 출력 수 복원, 라벨→포트 매핑.

### 비범위
- Loop/Batch. MCP 입력 스키마의 switch/merge 경로 인지(후속).
