# XpERP 더미 API 연동 테스트 본문 (copy & paste)

대상: `dummy-xperp-api` (:8000) · provider (:9000). 단지코드 `aptcd=001023`, 조회년월 `yearmon=202510` (스펙 examples 기준).

> 전제: provider DB가 비어 있는 상태에서 **이 스펙을 처음 등록**하면 operation id 는 아래와 같이 매겨집니다(삽입 순서).
> 1 `/impo/detail` · 4 `/recp/status` · 9 `/occp/unit` · 13 `/acct/summary` · 17 `/health` …
> **반드시 `GET /api/specs/1/operations` 로 id 를 먼저 확인**하고 다르면 본문의 `operation_id` 만 바꾸세요.

---

## 0) 스펙 등록 + id 확인
```bash
curl -X POST http://localhost:9000/api/specs/from-url -H "Content-Type: application/json" \
  -d "{\"url\":\"http://localhost:8000/openapi.json\",\"name\":\"xperp\"}"
# → operation_count: 17, base_url: null (실행 시 http://localhost:8000 로 폴백)

curl http://localhost:9000/api/specs/1/operations
```

---

## 시나리오 A — 단일 노드(관리비 부과 상세, op 1)
가장 단순. 워크플로우 생성 → 그래프 저장 → 실행.
```bash
# 워크플로우 생성
curl -X POST http://localhost:9000/api/workflows -H "Content-Type: application/json" -d "{\"name\":\"관리비조회\"}"
# 그래프 저장 (workflow id 가 1 이라고 가정)
curl -X PUT http://localhost:9000/api/workflows/1 -H "Content-Type: application/json" -d @- <<'JSON'
{
  "nodes": [
    {"id": "start", "type": "start"},
    {"id": "n1", "type": "api_call", "operation_id": 1,
     "params": {"query": {"aptcd": "001023", "yearmon": "202510", "dong": "101", "ho": "305"}}}
  ],
  "edges": [{"id": "e0", "source": "start", "target": "n1"}]
}
JSON
# 실행
curl -X POST http://localhost:9000/api/workflows/1/run -H "Content-Type: application/json" -d "{\"initial_input\":{}}"
```
기대: `status: success`, n1 output 에 `data.total_amount`, `data.items[...]`(공용관리비 등).

---

## 시나리오 B — 2노드 체인 + 데이터 매핑 (입주자 → 수납현황)
n1 `occp/unit`(op 9) 응답의 `data.dong / data.ho` 를 n2 `recp/status`(op 4) 쿼리로 자동 주입.
```bash
curl -X POST http://localhost:9000/api/workflows -H "Content-Type: application/json" -d "{\"name\":\"입주자-수납체인\"}"
# 위에서 받은 새 workflow id 사용 (예: 2)
curl -X PUT http://localhost:9000/api/workflows/2 -H "Content-Type: application/json" -d @- <<'JSON'
{
  "nodes": [
    {"id": "start", "type": "start"},
    {"id": "n1", "type": "api_call", "operation_id": 9,
     "params": {"query": {"aptcd": "001023", "dong": "101", "ho": "305"}}},
    {"id": "n2", "type": "api_call", "operation_id": 4,
     "params": {"query": {"aptcd": "001023", "yearmon": "202510"}}}
  ],
  "edges": [
    {"id": "e0", "source": "start", "target": "n1"},
    {"id": "e1", "source": "n1", "target": "n2",
     "data_mapping": [
       {"from": "$.data.dong", "to": "query.dong"},
       {"from": "$.data.ho",   "to": "query.ho"}
     ]}
  ]
}
JSON
curl -X POST http://localhost:9000/api/workflows/2/run -H "Content-Type: application/json" -d "{\"initial_input\":{}}"
```
기대: `status: success`. n2 호출 쿼리에 `dong=101, ho=305` 가 n1 응답에서 주입됨. n2 output `data.paid` 등 수납 정보 반환.
- 매핑 키는 `$.data.dong` 처럼 **응답 본문 기준 JSONPath**(더미 API는 `{success,is_dummy,data:{...}}` 로 감싸므로 `$.data.` 접두사 필요).

---

## 실패 케이스 확인
n1 에서 필수 `aptcd` 를 빼면 → 더미 API 가 422 → n1 `failed`, n2 `skipped`, 전체 `failed`(앱은 죽지 않음). `GET /api/executions/{id}` 로 로그 확인.

## Swagger UI 로도 가능
http://localhost:9000/docs 에서 위 본문을 그대로 "Try it out" 에 넣어 실행할 수 있습니다.
