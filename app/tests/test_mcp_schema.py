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
    assert "aptcd" in props
    assert "dong" in props
    # 분기 하위라 실행 여부가 런타임 의존 → required 에는 넣지 않음(과도제약 방지)
    assert "aptcd" not in sch.get("required", [])


# ---------- 2. start → api : 무조건 도달하는 필수 파라미터는 required ----------
def test_direct_api_required():
    graph = {
        "nodes": [{"id": "s", "type": "start"}, _api("a")],
        "edges": [{"source": "s", "target": "a"}],
    }
    sch = _schema(graph)
    assert "aptcd" in sch["properties"]
    assert "aptcd" in sch.get("required", [])
    assert "dong" not in sch.get("required", [])  # optional


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
    assert "aptcd" in props                      # 진입 노드(a1)
    assert not any(k.startswith("a2_") for k in props)  # 하류(a2) → 자동주입 → 제외


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
    assert "aptcd" not in sch["properties"]  # 정적값
    assert "dong" in sch["properties"]


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
    assert "aptcd" not in sch["properties"]  # 매핑으로 채워짐
    assert "dong" in sch["properties"]


# ---------- 5b. _input 표시 시: 정적값이 있어도 노출 + default 부여 ----------
def test_input_marked_static_exposed_with_default():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            _api("a", params={"query": {"aptcd": "095001"}, "_input": ["query.aptcd"]}),
        ],
        "edges": [{"source": "s", "target": "a"}],
    }
    sch = _schema(graph)
    assert "aptcd" in sch["properties"]                       # 입력 표시 → 노출
    assert sch["properties"]["aptcd"]["default"] == "095001"  # 기존값=기본값
    assert "aptcd" not in sch.get("required", [])             # 기본값 있으므로 required 제외


# ---------- 5c. _input 표시 + 엣지매핑이어도 노출(명시 입력 우선) ----------
def test_input_marked_overrides_edge_mapping():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            _api("a", params={"_input": ["query.aptcd"]}),
        ],
        "edges": [
            {"source": "s", "target": "a",
             "data_mapping": [{"from": "$.aptcd", "to": "query.aptcd"}]},
        ],
    }
    sch = _schema(graph)
    assert "aptcd" in sch["properties"]  # 매핑보다 명시 입력 우선


# ---------- 5d. _input 미사용 시 기존 정적값 제외 동작 유지(하위호환) ----------
def test_no_input_marker_keeps_legacy_behavior():
    graph = {
        "nodes": [
            {"id": "s", "type": "start"},
            _api("a", params={"query": {"aptcd": "095001"}}),
        ],
        "edges": [{"source": "s", "target": "a"}],
    }
    sch = _schema(graph)
    assert "aptcd" not in sch["properties"]  # 표시 없음 → 정적값 제외(기존)


# ---------- 6. apply_tool_args 라운드트립(스위치 하류 키 주입) ----------
def test_apply_tool_args_roundtrip():
    graph = {
        "nodes": [{"id": "s", "type": "start"}, _api("a")],
        "edges": [{"source": "s", "target": "a"}],
    }
    g = mcp_server.apply_tool_args(graph, {"a.query.aptcd": "095001"})
    node_a = {n["id"]: n for n in g["nodes"]}["a"]
    assert node_a["params"]["query"]["aptcd"] == "095001"


# ---------- 7. 평면 인자 이름 + 별칭(LangGraph 친화) ----------
def test_flat_names_and_alias():
    graph = {
        "nodes": [{"id": "3", "type": "start"}, _api("n")],
        "edges": [{"source": "3", "target": "n"}],
    }
    sch, alias = mcp_server.build_schema_and_alias(graph)
    # LLM 이 보게 될 인자 이름은 평면(aptcd/dong) — 노드 스코프 키가 아님
    assert set(sch["properties"]) == {"aptcd", "dong"}
    assert alias["aptcd"] == "n.query.aptcd"
    # 평면 인자 → 별칭 해석 → 노드 params 주입 라운드트립
    args = {"aptcd": "001023", "dong": "101"}
    resolved = {alias.get(k, k): v for k, v in args.items()}
    g = mcp_server.apply_tool_args(graph, resolved)
    node_n = {x["id"]: x for x in g["nodes"]}["n"]
    assert node_n["params"]["query"] == {"aptcd": "001023", "dong": "101"}


# ---------- 8. 이름 충돌 시 노드/위치로 자동 구분 ----------
def test_name_collision_disambiguated():
    graph = {
        "nodes": [{"id": "s", "type": "start"}, _api("a"), _api("b")],
        "edges": [{"source": "s", "target": "a"}, {"source": "s", "target": "b"}],
    }
    sch, alias = mcp_server.build_schema_and_alias(graph)
    # 두 진입 노드가 같은 aptcd/dong 을 노출 → 노드로 구분된 키
    assert "a_query_aptcd" in sch["properties"]
    assert "b_query_aptcd" in sch["properties"]
    assert alias["a_query_aptcd"] == "a.query.aptcd"
