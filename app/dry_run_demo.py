"""dry-run 동작 데모 (네트워크 의존 없음).

실행:  cd app  →  python dry_run_demo.py
- GET(조회) 노드는 dry-run에서도 실제 호출(여기선 mock)되어 미리보기 데이터 생성
- POST(변경) 노드는 호출되지 않고 'planned' 로 기록되어 planned_actions 에 모임
"""
import json
from engine import executor, http_client

# 조회(GET)는 dry-run에서 실제 호출되므로 mock 으로 대체(네트워크 불필요)
def _fake_get(method, base_url, path, **kw):
    return {"status_code": 200, "headers": {}, "body": {"dong": "101", "amount": 128000}}

http_client.call = _fake_get  # 데모용 주입

# 오퍼레이션 정의: op1=GET(조회), op2=POST(변경)
OPS = {
    1: {"method": "GET",  "path": "/impo/detail", "base_url": "http://xperp.local"},
    2: {"method": "POST", "path": "/recp/create",  "base_url": "http://xperp.local"},
}

graph = {
    "workflow_id": 999,
    "nodes": [
        {"id": "s", "type": "start"},
        {"id": "read",  "type": "api_call", "operation_id": 1, "params": {"query": {"dong": "101"}}},
        {"id": "write", "type": "api_call", "operation_id": 2,
         "params": {"body": {"dong": "101", "amount": 128000}}},
        {"id": "e", "type": "end"},
    ],
    "edges": [
        {"id": "e0", "source": "s",     "target": "read"},
        {"id": "e1", "source": "read",  "target": "write"},
        {"id": "e2", "source": "write", "target": "e"},
    ],
}

print("===== dry_run=True (계획만) =====")
res = executor.run_workflow(graph, initial_input={}, operation_resolver=lambda i: OPS[i], dry_run=True)
print("status      :", res["status"], "| dry_run:", res["dry_run"])
print("node status :", {l["node_key"]: l["status"] for l in res["logs"]})
print("planned_actions:")
print(json.dumps(res["planned_actions"], ensure_ascii=False, indent=2))

print("\n===== dry_run=False (실제 실행, 데모라 POST도 mock) =====")
res2 = executor.run_workflow(graph, initial_input={}, operation_resolver=lambda i: OPS[i])
print("status      :", res2["status"], "| dry_run:", res2["dry_run"])
print("node status :", {l["node_key"]: l["status"] for l in res2["logs"]})
print("planned_actions:", res2["planned_actions"])
