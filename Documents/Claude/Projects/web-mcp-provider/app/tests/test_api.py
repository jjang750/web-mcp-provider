"""3단계 API 통합 테스트 — 스펙 업로드→워크플로우→실행→조회 라운드트립.

외부 HTTP 는 engine.http_client.call 을 monkeypatch 하여 격리한다.
"""
import io
import json

import pytest
from starlette.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # 테스트 전용 임시 DB
    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "t.db"))
    # 모듈 재로딩으로 DB_PATH 반영
    import importlib

    import backend.db as db
    importlib.reload(db)
    import backend.repositories.specs as s
    import backend.repositories.workflows as w
    import backend.repositories.executions as e
    importlib.reload(s); importlib.reload(w); importlib.reload(e)
    import backend.app as app_mod
    importlib.reload(app_mod)
    db.init_db()
    with TestClient(app_mod.app) as c:
        yield c


SPEC = json.dumps({
    "openapi": "3.0.0",
    "servers": [{"url": "http://localhost:8000"}],
    "paths": {
        "/users/{id}": {
            "get": {"operationId": "getUser", "summary": "사용자 조회",
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                    "responses": {"200": {"description": "ok"}}}
        }
    }
})


def test_full_roundtrip(client, monkeypatch):
    from engine import http_client
    monkeypatch.setattr(
        http_client, "call",
        lambda *a, **k: {"status_code": 200, "headers": {}, "body": {"id": 1, "name": "kim"}},
    )

    # 1) 스펙 업로드
    r = client.post("/api/specs/upload",
                    files={"file": ("api.json", io.BytesIO(SPEC.encode()), "application/json")})
    assert r.status_code == 200, r.text
    spec = r.json()
    assert spec["operation_count"] == 1
    spec_id = spec["spec_id"]

    # 2) 오퍼레이션 목록/단건
    ops = client.get(f"/api/specs/{spec_id}/operations").json()
    assert len(ops) == 1
    op_id = ops[0]["id"]
    assert client.get(f"/api/operations/{op_id}").json()["method"] == "GET"

    # 3) 워크플로우 생성
    wf = client.post("/api/workflows", json={"name": "테스트", "description": "d"}).json()
    wf_id = wf["id"]
    assert wf_id in [x["id"] for x in client.get("/api/workflows").json()]

    # 4) 그래프 저장(PUT)
    body = {
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
            {"id": "n1", "type": "api_call", "operation_id": op_id,
             "params": {"path": {"id": 1}}, "position": {"x": 200, "y": 0}},
        ],
        "edges": [{"id": "e0", "source": "start", "target": "n1", "data_mapping": []}],
    }
    detail = client.put(f"/api/workflows/{wf_id}", json=body).json()
    assert len(detail["nodes"]) == 2 and len(detail["edges"]) == 1

    # 5) 실행
    run = client.post(f"/api/workflows/{wf_id}/run", json={"initial_input": {}}).json()
    assert run["status"] == "success"
    exec_id = run["execution_id"]
    assert exec_id is not None

    # 6) 실행 결과 조회
    got = client.get(f"/api/executions/{exec_id}").json()
    assert got["status"] == "success"
    statuses = {l["node_key"]: l["status"] for l in got["logs"]}
    assert statuses == {"start": "success", "n1": "success"}

    # 7) MCP 노출
    exp = client.put(f"/api/workflows/{wf_id}/expose",
                     json={"exposed": True, "group": "xperp", "tool_name": "get_user"}).json()
    assert exp["mcp_exposed"] is True and exp["mcp_group"] == "xperp"

    # 8) 삭제
    assert client.delete(f"/api/workflows/{wf_id}").json()["deleted"] is True
    assert client.get(f"/api/workflows/{wf_id}").status_code == 404


def test_run_failure_persists_skip(client, monkeypatch):
    from engine import http_client
    monkeypatch.setattr(
        http_client, "call",
        lambda *a, **k: {"status_code": 401, "headers": {}, "body": {"error": "no"}},
    )
    client.post("/api/specs/upload",
                files={"file": ("api.json", io.BytesIO(SPEC.encode()), "application/json")})
    op_id = client.get("/api/specs/1/operations").json()[0]["id"]
    wf_id = client.post("/api/workflows", json={"name": "f"}).json()["id"]
    body = {
        "nodes": [
            {"id": "n1", "type": "api_call", "operation_id": op_id, "params": {}},
            {"id": "n2", "type": "api_call", "operation_id": op_id, "params": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    client.put(f"/api/workflows/{wf_id}", json=body)
    run = client.post(f"/api/workflows/{wf_id}/run", json={"initial_input": {}}).json()
    assert run["status"] == "failed"
    statuses = {l["node_key"]: l["status"] for l in run["logs"]}
    assert statuses["n1"] == "failed" and statuses["n2"] == "skipped"
