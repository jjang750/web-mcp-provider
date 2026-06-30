"""MCP 입력 스키마 분기 인지 테스트.

build_input_schema 가 start 에서 전방 도달 가능한 '진입 api 노드'의 파라미터를
분기(switch/condition/filter)를 거치더라도 누락하지 않는지 검증한다.
"""
import pytest

pytest.importorskip("mcp")  # mcp 미설치 환경에서는 스킵

from backend import mcp_server


# ---------- 오퍼레이션 mock ----------
# operation_id -> operation dict (params_schema 만 사용)
_OPS = {
    1: {
        "id": 1, "method": "GET", "path": "/impo",
        "params_schema": [
            {"in": "query", "name": "aptcd", "required": True,
             "schema": {"type": "string"}, "description": "단지코드"},
            {"in": "query", "name": "dong", "required": False,
             "schema": {"type": "string"}, "description": "동"},
        ],
    },
}


@pytest.fixture(autouse=True)
def _patch_ops(monkeypatch):
    monkeypatch.setattr(mcp_server.specs_repo, "get_operation", lambda oid: _OPS.get(oid))


def _api(nid, op_id=1, params=None):
    return {"id": nid, "type": "api_call", "operation_id": op_id, "params": params or {}}


def _schema(graph):
    return mcp_server.build_input_schema(graph)


# ---------- 1. start → switch → api : 하류 api 필수 파라미터가 누락되지 않음(핵심 버그) ----------
def test_switch_downstream_api_params_present():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "sw", "type": "switch", "params": {"switch": {"left": "$.data.aptcd", "cases": ["095"]}}},
            _api("a"),
        ],
        "edges": [
            {"source": "s", "target": "sw"},
            {"source": "sw", "target": "a", "label": "095"},
        ],
    }
    sch = _schema(graph)
    props = sch["properties"]
    # 분기를 거친 하류 api 의 파라미터가 properties 에 포함되어야 함(이전엔 누락됨)
    assert "a.query.aptcd" in props
    assert "a.query.dong" in props
    # 분기 하위라 실행 여부가 런타임 의존 → required 에는 넣지 않음(과도제약 방지)
    assert "a.query.aptcd" not in sch.get("required", [])


# ---------- 2. start → api : 무조건 도달하는 필수 파라미터는 required ----------
def test_direct_api_required():
    graph = {
        "nodes": [{"id": "s", "type": "start"}, _api("a")],
        "edges": [{"source": "s", "target": "a"}],
    }
    sch = _schema(graph)
    assert "a.query.aptcd" in sch["properties"]
    assert "a.query.aptcd" in sch.get("required", [])
    assert "a.query.dong" not in sch.get("required", [])  # optional


# ---------- 3. 하류 api(상류 생산자 존재)는 자동주입 대상 → 스키마에서 제외 ----------
def test_downstream_producer_excluded():
    graph = {
        "nodes": [{"id": "s", "type": "start"}, _api("a1"), _api("a2")],
        "edges": [
            {"source": "s", "target": "a1"},
            {"source": "a1", "target": "a2"},
        ],
    }
    sch = _schema(graph)
    props = sch["properties"]
    assert "a1.query.aptcd" in props          # 진입 노드
    assert not any(k.startswith("a2.") for k in props)  # 하류 → 자동주입 → 제외


# ---------- 4. 정적값으로 채워진 파라미터는 제외 ----------
def test_static_value_excluded():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            _api("a", params={"query": {"aptcd": "095001"}}),
        ],
        "edges": [{"source": "s", "target": "a"}],
    }
    sch = _schema(graph)
    assert "a.query.aptcd" not in sch["properties"]  # 정적값
    assert "a.query.dong" in sch["properties"]


# ---------- 5. 엣지 data_mapping 으로 채워지는 파라미터는 제외 ----------
def test_edge_mapping_excluded():
    graph = {
        "nodes": [{"id": "s", "type": "start"}, _api("a")],
        "edges": [
            {"source": "s", "target": "a",
             "data_mapping": [{"from": "$.aptcd", "to": "query.aptcd"}]},
        ],
    }
    sch = _schema(graph)
    assert "a.query.aptcd" not in sch["properties"]  # 매핑으로 채워짐
    assert "a.query.dong" in sch["properties"]


# ---------- 6. apply_tool_args 라운드트립(스위치 하류 키 주입) ----------
def test_apply_tool_args_roundtrip():
    graph = {
        "nodes": [{"id": "s", "type": "start"}, _api("a")],
        "edges": [{"source": "s", "target": "a"}],
    }
    g = mcp_server.apply_tool_args(graph, {"a.query.aptcd": "095001"})
    node_a = {n["id"]: n for n in g["nodes"]}["a"]
    assert node_a["params"]["query"]["aptcd"] == "095001"
