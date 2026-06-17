import pytest

from engine import executor, http_client


# ---------- JSONPath 부분집합 ----------
def test_get_by_path_root_dot_index():
    data = {"a": {"b": [10, {"c": 99}]}}
    assert executor.get_by_path(data, "$") == data
    assert executor.get_by_path(data, "$.a.b[0]") == 10
    assert executor.get_by_path(data, "$.a.b[1].c") == 99
    assert executor.get_by_path(data, "$.a.x") is None


def test_set_by_path_strips_params_prefix():
    params = {}
    executor.set_by_path(params, "params.path.id", 5)
    executor.set_by_path(params, "query.q", "k")
    assert params == {"path": {"id": 5}, "query": {"q": "k"}}


# ---------- 그래프 검증 ----------
def test_cycle_rejected():
    graph = {
        "workflow_id": 1,
        "nodes": [{"id": "a", "type": "transform"}, {"id": "b", "type": "transform"}],
        "edges": [
            {"id": "e1", "source": "a", "target": "b"},
            {"id": "e2", "source": "b", "target": "a"},
        ],
    }
    with pytest.raises(ValueError):
        executor.validate_graph(graph)


def test_topological_order_linear():
    graph = {
        "workflow_id": 1,
        "nodes": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        "edges": [
            {"id": "e1", "source": "a", "target": "b"},
            {"id": "e2", "source": "b", "target": "c"},
        ],
    }
    assert executor.topological_order(graph) == ["a", "b", "c"]


# ---------- 순차 실행 ----------
def _resolver(_id):
    return {"method": "GET", "path": "/n/{id}", "base_url": "http://op.example.com"}


def test_sequential_success_with_mapping(monkeypatch):
    calls = []

    def fake_call(method, base_url, path, **kw):
        calls.append((base_url, path, kw.get("path_params")))
        return {"status_code": 200, "headers": {}, "body": {"id": 7, "name": "kim"}}

    monkeypatch.setattr(http_client, "call", fake_call)

    graph = {
        "workflow_id": 1,
        "nodes": [
            {"id": "start", "type": "start"},
            {"id": "n1", "type": "api_call", "operation_id": 1,
             "params": {"path": {"id": 1}}},
            {"id": "n2", "type": "api_call", "operation_id": 2,
             "base_url": "http://node.example.com", "params": {"path": {}}},
        ],
        "edges": [
            {"id": "e0", "source": "start", "target": "n1"},
            {"id": "e1", "source": "n1", "target": "n2",
             "data_mapping": [{"from": "$.id", "to": "params.path.id"}]},
        ],
    }
    res = executor.run_workflow(graph, initial_input={"x": 1}, operation_resolver=_resolver)
    assert res["status"] == "success"
    # n2 는 node.base_url 우선
    assert calls[1][0] == "http://node.example.com"
    # n1 출력 id=7 이 n2 path.id 로 매핑됨
    assert calls[1][2] == {"id": 7}
    statuses = {l["node_key"]: l["status"] for l in res["logs"]}
    assert statuses == {"start": "success", "n1": "success", "n2": "success"}


def test_failure_skips_downstream(monkeypatch):
    def fake_call(method, base_url, path, **kw):
        return {"status_code": 401, "headers": {}, "body": {"error": "unauthorized"}}

    monkeypatch.setattr(http_client, "call", fake_call)

    graph = {
        "workflow_id": 1,
        "nodes": [
            {"id": "n1", "type": "api_call", "operation_id": 1, "params": {}},
            {"id": "n2", "type": "api_call", "operation_id": 2, "params": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    res = executor.run_workflow(graph, operation_resolver=_resolver)
    assert res["status"] == "failed"
    statuses = {l["node_key"]: l["status"] for l in res["logs"]}
    assert statuses["n1"] == "failed"
    assert statuses["n2"] == "skipped"


def test_no_raise_on_network_error(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(http_client, "call", boom)
    graph = {
        "workflow_id": 1,
        "nodes": [{"id": "n1", "type": "api_call", "operation_id": 1, "params": {}}],
        "edges": [],
    }
    res = executor.run_workflow(graph, operation_resolver=_resolver)  # raise 하지 않음
    assert res["status"] == "failed"
    assert res["logs"][0]["status"] == "failed"
    assert "connection refused" in res["logs"][0]["error"]
