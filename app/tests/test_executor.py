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


def test_connection_base_url_and_auth_resolution(monkeypatch):
    """연결(API) base_url/인증이 노드에 자동 적용되는지.
    우선순위: base_url(node→conn→op→default), auth(conn→run)."""
    captured = []

    def fake_call(method, base_url, path, **kw):
        captured.append({"base_url": base_url, "auth": kw.get("auth")})
        return {"status_code": 200, "headers": {}, "body": {"ok": True}}

    monkeypatch.setattr(http_client, "call", fake_call)

    def resolver(op_id):
        if op_id == 1:  # 연결 base_url + bearer 인증 보유, node override 없음
            return {"method": "GET", "path": "/a", "base_url": "http://op.example.com",
                    "conn_base_url": "http://conn.example.com",
                    "auth": {"type": "bearer", "token": "T"}}
        return {"method": "GET", "path": "/b", "base_url": "http://op2.example.com",
                "conn_base_url": None, "auth": None}  # 연결 인증 없음 → run auth 폴백

    graph = {
        "workflow_id": 1,
        "nodes": [
            {"id": "n1", "type": "api_call", "operation_id": 1, "params": {}},
            {"id": "n2", "type": "api_call", "operation_id": 2, "params": {}},
        ],
        "edges": [{"id": "e1", "source": "n1", "target": "n2"}],
    }
    res = executor.run_workflow(graph, auth={"type": "apikey", "name": "X", "value": "K"},
                                operation_resolver=resolver)
    assert res["status"] == "success"
    # n1: 연결 base_url 우선, 연결 인증 적용
    assert captured[0]["base_url"] == "http://conn.example.com"
    assert captured[0]["auth"] == {"type": "bearer", "token": "T"}
    # n2: 연결 base_url 없음 → op base_url, 연결 인증 없음 → run auth 폴백
    assert captured[1]["base_url"] == "http://op2.example.com"
    assert captured[1]["auth"] == {"type": "apikey", "name": "X", "value": "K"}


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


# ---------- 조건(IF) 분기 ----------
def test_eval_condition_ops():
    subj = {"status": "active", "count": 5, "items": [1, 2]}
    assert executor.eval_condition(subj, {"left": "$.status", "op": "==", "right": "active"}) is True
    assert executor.eval_condition(subj, {"left": "$.status", "op": "!=", "right": "x"}) is True
    assert executor.eval_condition(subj, {"left": "$.count", "op": ">", "right": 3}) is True
    assert executor.eval_condition(subj, {"left": "$.count", "op": "<=", "right": 5}) is True
    assert executor.eval_condition(subj, {"left": "$.missing", "op": "exists"}) is False
    assert executor.eval_condition(subj, {"left": "$.status", "op": "truthy"}) is True
    assert executor.eval_condition(subj, {"left": "$.items", "op": "contains", "right": 2}) is True
    # 숫자/문자 혼합 비교 관용
    assert executor.eval_condition(subj, {"left": "$.count", "op": "==", "right": "5"}) is True


def _branch_graph():
    return {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "c", "type": "condition",
             "params": {"condition": {"left": "$.flag", "op": "==", "right": "yes"}}},
            {"id": "a", "type": "transform"},
            {"id": "b", "type": "transform"},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "c"},
            {"id": "e2", "source": "c", "target": "a", "label": "true"},
            {"id": "e3", "source": "c", "target": "b", "label": "false"},
        ],
    }


def _status_map(res):
    return {l["node_key"]: l["status"] for l in res["logs"]}


def test_condition_true_path():
    res = executor.run_workflow(_branch_graph(), initial_input={"flag": "yes"},
                                operation_resolver=lambda _i: None)
    st = _status_map(res)
    assert st["c"] == "success"
    assert st["a"] == "success"
    assert st["b"] == "skipped"
    assert res["status"] == "success"
    clog = next(l for l in res["logs"] if l["node_key"] == "c")
    assert clog["output"]["branch"] == "true"
    assert clog["output"]["expr"] == "$.flag == yes"
    assert clog["output"]["result"] is True


def test_condition_false_path():
    res = executor.run_workflow(_branch_graph(), initial_input={"flag": "no"},
                                operation_resolver=lambda _i: None)
    st = _status_map(res)
    assert st["a"] == "skipped"
    assert st["b"] == "success"


def test_condition_merge_rejoin_not_skipped():
    graph = _branch_graph()
    graph["nodes"].append({"id": "m", "type": "transform"})
    graph["edges"].append({"id": "e4", "source": "a", "target": "m"})
    graph["edges"].append({"id": "e5", "source": "b", "target": "m"})
    res = executor.run_workflow(graph, initial_input={"flag": "yes"},
                                operation_resolver=lambda _i: None)
    st = _status_map(res)
    assert st["a"] == "success"
    assert st["b"] == "skipped"
    # 양쪽에서 도달 가능한 합류 노드는 스킵되지 않아야 함
    assert st["m"] == "success"


# ---------- Switch / Merge / Filter ----------
def _switch_graph():
    return {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "sw", "type": "switch",
             "params": {"switch": {"left": "$.status", "cases": ["active", "pending"]}}},
            {"id": "A", "type": "transform"},
            {"id": "P", "type": "transform"},
            {"id": "D", "type": "transform"},
        ],
        "edges": [
            {"id": "e0", "source": "s", "target": "sw"},
            {"id": "e1", "source": "sw", "target": "A", "label": "active"},
            {"id": "e2", "source": "sw", "target": "P", "label": "pending"},
            {"id": "e3", "source": "sw", "target": "D", "label": "__default__"},
        ],
    }


def test_switch_case_match():
    res = executor.run_workflow(_switch_graph(), initial_input={"status": "active"},
                                operation_resolver=lambda _i: None)
    st = _status_map(res)
    assert st["A"] == "success" and st["P"] == "skipped" and st["D"] == "skipped"


def test_switch_default():
    res = executor.run_workflow(_switch_graph(), initial_input={"status": "zzz"},
                                operation_resolver=lambda _i: None)
    st = _status_map(res)
    assert st["D"] == "success" and st["A"] == "skipped" and st["P"] == "skipped"


def test_filter_pass_and_block():
    def g():
        return {
            "workflow_id": 1,
            "nodes": [
                {"id": "s", "type": "start"},
                {"id": "f", "type": "filter",
                 "params": {"condition": {"left": "$.ok", "op": "==", "right": "yes"}}},
                {"id": "n", "type": "transform"},
            ],
            "edges": [
                {"id": "e1", "source": "s", "target": "f"},
                {"id": "e2", "source": "f", "target": "n"},
            ],
        }
    r1 = executor.run_workflow(g(), initial_input={"ok": "yes"}, operation_resolver=lambda _i: None)
    assert _status_map(r1)["n"] == "success"
    r2 = executor.run_workflow(g(), initial_input={"ok": "no"}, operation_resolver=lambda _i: None)
    s2 = _status_map(r2)
    assert s2["f"] == "success" and s2["n"] == "skipped"  # 걸러짐


def test_merge_collects_incoming():
    graph = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "c", "type": "condition",
             "params": {"condition": {"left": "$.flag", "op": "==", "right": "yes"}}},
            {"id": "a", "type": "transform", "params": {"v": 1}},
            {"id": "b", "type": "transform", "params": {"v": 2}},
            {"id": "m", "type": "merge"},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "c"},
            {"id": "e2", "source": "c", "target": "a", "label": "true"},
            {"id": "e3", "source": "c", "target": "b", "label": "false"},
            {"id": "e4", "source": "a", "target": "m"},
            {"id": "e5", "source": "b", "target": "m"},
        ],
    }
    res = executor.run_workflow(graph, initial_input={"flag": "yes"}, operation_resolver=lambda _i: None)
    st = _status_map(res)
    assert st["m"] == "success"
    mlog = next(l for l in res["logs"] if l["node_key"] == "m")
    # true 경로만 살아있으므로 a 출력만 합류, b 는 스킵되어 없음
    assert "a" in mlog["output"] and "b" not in mlog["output"]


# ---------- end 언래핑 / final ----------
def test_end_single_source_passthrough_and_final():
    g = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "n", "type": "transform", "params": {"v": 1}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "n"},
            {"id": "e2", "source": "n", "target": "e"},
        ],
    }
    res = executor.run_workflow(g, initial_input={}, operation_resolver=lambda _i: None)
    endlog = next(l for l in res["logs"] if l["node_key"] == "e")
    assert endlog["output"] == {"v": 1}      # 노드ID로 감싸지 않음
    assert res["final"] == {"v": 1}


def test_end_multi_source_list():
    g = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "a", "type": "transform", "params": {"v": 1}},
            {"id": "b", "type": "transform", "params": {"v": 2}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "a"},
            {"id": "e2", "source": "s", "target": "b"},
            {"id": "e3", "source": "a", "target": "e"},
            {"id": "e4", "source": "b", "target": "e"},
        ],
    }
    res = executor.run_workflow(g, initial_input={}, operation_resolver=lambda _i: None)
    endlog = next(l for l in res["logs"] if l["node_key"] == "e")
    assert isinstance(endlog["output"], list) and {"v": 1} in endlog["output"]


# ---------- bool ↔ "true"/"false" 비교 ----------
def test_eval_condition_bool_vs_string():
    # JSON 불리언 true 와 우변 문자열 "true" 가 같아야 함
    assert executor.eval_condition({"success": True}, {"left": "$.success", "op": "==", "right": "true"}) is True
    assert executor.eval_condition({"success": False}, {"left": "$.success", "op": "==", "right": "true"}) is False
    assert executor.eval_condition({"success": False}, {"left": "$.success", "op": "==", "right": "false"}) is True
    assert executor.eval_condition({"success": True}, {"left": "$.success", "op": "!=", "right": "false"}) is True
    # truthy 도 동작
    assert executor.eval_condition({"success": True}, {"left": "$.success", "op": "truthy"}) is True


# ---------- 우변 타입(rtype) 지정 ----------
def test_eval_condition_rtype():
    ec = executor.eval_condition
    # string: 숫자처럼 보여도 문자열로 비교
    assert ec({"v": "001"}, {"left": "$.v", "op": "==", "right": "001", "rtype": "string"}) is True
    assert ec({"v": 1}, {"left": "$.v", "op": "==", "right": "1", "rtype": "string"}) is True
    # number: 문자열 "100" 과 숫자 100 동등
    assert ec({"v": "100"}, {"left": "$.v", "op": "==", "right": 100, "rtype": "number"}) is True
    assert ec({"v": 100}, {"left": "$.v", "op": ">", "right": "50", "rtype": "number"}) is True
    # boolean
    assert ec({"v": True}, {"left": "$.v", "op": "==", "right": "true", "rtype": "boolean"}) is True
    assert ec({"v": False}, {"left": "$.v", "op": "!=", "right": "true", "rtype": "boolean"}) is True
    # null
    assert ec({"v": None}, {"left": "$.v", "op": "==", "right": "", "rtype": "null"}) is True
    assert ec({"v": 0}, {"left": "$.v", "op": "==", "right": "", "rtype": "null"}) is False
    # auto(기본): 기존 관용 비교 유지
    assert ec({"v": True}, {"left": "$.v", "op": "==", "right": "true"}) is True


def test_end_dedupes_same_source():
    # IF 의 true/false 포트를 둘 다 end 로 연결 → 같은 상류이므로 배열이 아니라 단일 값
    g = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "c", "type": "condition", "params": {"condition": {"left": "$.ok", "op": "==", "right": "true"}}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "c"},
            {"id": "e2", "source": "c", "target": "e", "label": "true"},
            {"id": "e3", "source": "c", "target": "e", "label": "false"},
        ],
    }
    res = executor.run_workflow(g, initial_input={"ok": True}, operation_resolver=lambda _i: None)
    endlog = next(l for l in res["logs"] if l["node_key"] == "e")
    assert endlog["output"] == {"ok": True}          # 배열 아님
    assert not isinstance(endlog["output"], list)


# ---------- 변환(Set) 노드 ----------
def test_transform_setmap_picks_fields():
    g = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "t", "type": "transform", "params": {"setmap": [
                {"key": "dong", "mode": "path", "src": "$.data.dong"},
                {"key": "amount", "mode": "path", "src": "$.data.total_amount"},
                {"key": "src_apt", "mode": "literal", "value": "095001"},
            ]}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "e1", "source": "s", "target": "t"},
            {"id": "e2", "source": "t", "target": "e"},
        ],
    }
    subj = {"data": {"dong": "101", "total_amount": 128000, "etc": "x"}}
    res = executor.run_workflow(g, initial_input=subj, operation_resolver=lambda _i: None)
    endlog = next(l for l in res["logs"] if l["node_key"] == "e")
    assert endlog["output"] == {"dong": "101", "amount": 128000, "src_apt": "095001"}


# ---------- 하류 노드 OUTPUT 자동 주입 ----------
def test_downstream_auto_binds_from_upstream(monkeypatch):
    calls = {}

    def fake_call(method, base_url, path, **kw):
        calls[path] = kw.get("query")
        if path == "/impo/detail":
            return {"status_code": 200, "headers": {}, "body": {"data": {"aptcd": "095001", "dong": "101"}}}
        return {"status_code": 200, "headers": {}, "body": {"ok": True}}

    monkeypatch.setattr(http_client, "call", fake_call)
    ops = {1: {"method": "GET", "path": "/impo/detail", "base_url": "http://x"},
           2: {"method": "GET", "path": "/recp/status", "base_url": "http://x"}}
    g = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "a1", "type": "api_call", "operation_id": 1, "params": {"query": {}}},
            {"id": "a2", "type": "api_call", "operation_id": 2, "params": {"query": {"aptcd": "", "dong": ""}}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "e0", "source": "s", "target": "a1"},
            {"id": "e1", "source": "a1", "target": "a2"},
            {"id": "e2", "source": "a2", "target": "e"},
        ],
    }
    executor.run_workflow(g, initial_input={}, operation_resolver=lambda i: ops[i])
    assert calls["/recp/status"] == {"aptcd": "095001", "dong": "101"}  # 매핑 없이 자동 주입


# ---------- dry-run (실행 계획 → 확인 → 실행) ----------
def test_is_read_only_inference_and_override():
    # 메서드 추론
    assert executor.is_read_only({"type": "api_call"}, {"method": "GET"}) is True
    assert executor.is_read_only({"type": "api_call"}, {"method": "POST"}) is False
    assert executor.is_read_only({"type": "api_call"}, {"method": "delete"}) is False
    # 제어흐름/변환 노드는 항상 조회로 간주
    assert executor.is_read_only({"type": "transform"}, None) is True
    # 명시 플래그가 메서드 추론보다 우선
    assert executor.is_read_only({"type": "api_call", "read_only": True}, {"method": "POST"}) is True
    assert executor.is_read_only({"type": "api_call", "read_only": False}, {"method": "GET"}) is False


def test_dry_run_plans_write_without_calling(monkeypatch):
    """dry_run: 변경(POST) 노드는 실제 호출하지 않고 planned 로 기록."""
    calls = []

    def fake_call(method, base_url, path, **kw):
        calls.append((method, path))
        return {"status_code": 200, "headers": {}, "body": {"ok": True}}

    monkeypatch.setattr(http_client, "call", fake_call)
    ops = {1: {"method": "POST", "path": "/recp/create", "base_url": "http://x"}}
    g = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "w", "type": "api_call", "operation_id": 1, "params": {"body": {"amount": 1000}}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "e0", "source": "s", "target": "w"},
            {"id": "e1", "source": "w", "target": "e"},
        ],
    }
    res = executor.run_workflow(g, initial_input={}, operation_resolver=lambda i: ops[i], dry_run=True)
    assert calls == []  # 변경 호출 미실행
    assert res["dry_run"] is True
    assert res["status"] == "success"
    st = _status_map(res)
    assert st["w"] == "planned"
    assert len(res["planned_actions"]) == 1
    pa = res["planned_actions"][0]
    assert pa["node_key"] == "w" and pa["method"] == "POST"
    assert pa["url"] == "http://x/recp/create" and pa["body"] == {"amount": 1000}


def test_dry_run_still_executes_read_calls(monkeypatch):
    """dry_run 이라도 조회(GET) 노드는 실제 호출해 미리보기 데이터를 만든다."""
    calls = []

    def fake_call(method, base_url, path, **kw):
        calls.append((method, path))
        return {"status_code": 200, "headers": {}, "body": {"dong": "101"}}

    monkeypatch.setattr(http_client, "call", fake_call)
    ops = {1: {"method": "GET", "path": "/impo/detail", "base_url": "http://x"}}
    g = {
        "workflow_id": 1,
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "r", "type": "api_call", "operation_id": 1, "params": {"query": {}}},
            {"id": "e", "type": "end"},
        ],
        "edges": [
            {"id": "e0", "source": "s", "target": "r"},
            {"id": "e1", "source": "r", "target": "e"},
        ],
    }
    res = executor.run_workflow(g, initial_input={}, operation_resolver=lambda i: ops[i], dry_run=True)
    assert calls == [("GET", "/impo/detail")]  # 조회는 실행됨
    assert _status_map(res)["r"] == "success"
    assert res["planned_actions"] == []
    assert res["final"] == {"dong": "101"}


def test_non_dry_run_executes_write(monkeypatch):
    """기본(dry_run=False)에서는 변경 노드도 실제 실행(하위 호환)."""
    calls = []

    def fake_call(method, base_url, path, **kw):
        calls.append((method, path))
        return {"status_code": 200, "headers": {}, "body": {"ok": True}}

    monkeypatch.setattr(http_client, "call", fake_call)
    ops = {1: {"method": "POST", "path": "/recp/create", "base_url": "http://x"}}
    g = {
        "workflow_id": 1,
        "nodes": [{"id": "w", "type": "api_call", "operation_id": 1, "params": {"body": {"a": 1}}}],
        "edges": [],
    }
    res = executor.run_workflow(g, initial_input={}, operation_resolver=lambda i: ops[i])
    assert calls == [("POST", "/recp/create")]
    assert res["dry_run"] is False
    assert res["planned_actions"] == []


def test_dry_run_preview_masks_secret(monkeypatch):
    """planned_actions 는 인증 시크릿을 노출하지 않고 type 만 표기."""
    monkeypatch.setattr(http_client, "call", lambda *a, **k: {"status_code": 200, "headers": {}, "body": {}})
    ops = {1: {"method": "POST", "path": "/x", "base_url": "http://x",
               "auth": {"type": "bearer", "token": "SECRET"}}}
    g = {
        "workflow_id": 1,
        "nodes": [{"id": "w", "type": "api_call", "operation_id": 1, "params": {}}],
        "edges": [],
    }
    res = executor.run_workflow(g, operation_resolver=lambda i: ops[i], dry_run=True)
    pa = res["planned_actions"][0]
    assert pa["auth_type"] == "bearer"
    assert "SECRET" not in json_dumps(pa)


def json_dumps(o):
    import json
    return json.dumps(o, ensure_ascii=False)
