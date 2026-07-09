"""MCP 서버 (stdio) — mcp_exposed=1 워크플로우를 외부 MCP 클라이언트(Claude Desktop 등)에 도구로 노출.

실행:  PYTHONPATH=<repo> python -m backend.mcp_server
  - MCP_GROUP 환경변수가 있으면 해당 그룹 워크플로우만 노출.
  - 도구 목록 갱신(재시작 불필요): 변경 감지 캐시 + tools/list_changed 알림.
    · list_tools 호출 시마다 변경 시그니처(노출 워크플로우 COUNT, MAX(updated_at))를 가벼운 1쿼리로 확인,
      바뀐 경우에만 재빌드 → 새 연결/재조회는 항상 최신.
    · 백그라운드 폴러(MCP_POLL_SECS, 기본 5초)가 변경을 감지하면 send_tool_list_changed 로 알림 →
      지원 클라이언트는 재시작 없이 자동 갱신(클라이언트 미지원 시 폴백=재조회/재연결 시 반영).
  - MCP_POLL_SECS=0 이면 폴러 비활성(기존처럼 기동 시 1회 + list 호출 시 갱신만).
"""
from __future__ import annotations

import asyncio
import copy
import json
import os
import re

from backend.db import init_db
from backend.repositories import specs as specs_repo
from backend.repositories import workflows as wf_repo
from backend.repositories import executions as exec_repo
from engine import executor

import mcp.types as types
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server

MCP_GROUP = os.environ.get("MCP_GROUP")
SERVER_NAME = os.environ.get("MCP_SERVER_NAME") or ("mcp-" + MCP_GROUP if MCP_GROUP else "mcp-provider")
try:
    POLL_SECS = float(os.environ.get("MCP_POLL_SECS", "5"))
except ValueError:
    POLL_SECS = 5.0

server = Server(SERVER_NAME)
_TOOLS: dict[str, dict] = {}  # tool_name -> {"wf":..., "graph":..., "schema":...}
_TOOLS_SIG: tuple | None = None  # 마지막으로 빌드한 노출 워크플로우 변경 시그니처
_SESSION = None  # list_tools 핸들러에서 캡처한 현재 세션(백그라운드 알림용)


# ---------- 헬퍼 ----------
def load_exposed_workflows() -> list[dict]:
    out = []
    for w in wf_repo.list_all():
        if not w.get("mcp_exposed"):
            continue
        if MCP_GROUP and (w.get("mcp_group") or "") != MCP_GROUP:
            continue
        out.append(w)
    return out


def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name or "")[:64] or "tool"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (name or "").lower()).strip("_")


def build_tool_name(wf_id: int, name: str, override: str | None = None) -> str:
    if override:
        return _sanitize(override)
    slug = _slug(name)
    return f"workflow_{wf_id}_{slug}" if slug else f"workflow_{wf_id}"


def _norm_dest(dest: str):
    """엣지 data_mapping 의 to 표현을 (loc, pname) 로 정규화.
    'query.x' / 'params.query.x' / '$.query.x' 모두 ('query','x'). 인식 불가 시 None."""
    d = (dest or "").strip()
    if d.startswith("$."):
        d = d[2:]
    parts = [s for s in d.split(".") if s]
    if parts and parts[0] == "params":
        parts = parts[1:]
    if len(parts) >= 2 and parts[0] in ("path", "query", "header", "body"):
        return parts[0], ".".join(parts[1:])
    return None


def _forward_reachable(graph: dict, starts: list[str]) -> set[str]:
    """starts 에서 엣지를 따라 전방 도달 가능한 노드 집합(starts 자신 제외)."""
    adj: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        adj.setdefault(e["source"], []).append(e["target"])
    seen: set[str] = set()
    stack = list(starts)
    while stack:
        n = stack.pop()
        for t in adj.get(n, []):
            if t not in seen:
                seen.add(t)
                stack.append(t)
    return seen


def _guaranteed_reachable(graph: dict, starts: list[str], nodes: dict) -> set[str]:
    """분기(condition/switch/filter)를 거치지 않고 '무조건' 도달하는 노드 집합.
    분기 노드의 하류는 런타임 분기 선택에 따라 실행 여부가 달라지므로 제외(과도제약 방지)."""
    adj: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        adj.setdefault(e["source"], []).append(e["target"])
    seen: set[str] = set()
    visited_src: set[str] = set()
    stack = list(starts)
    while stack:
        n = stack.pop()
        if n in visited_src:
            continue
        visited_src.add(n)
        if (nodes.get(n) or {}).get("type") in ("condition", "switch", "filter"):
            continue  # 분기 하위는 무조건 도달 아님 → 전파 중단
        for t in adj.get(n, []):
            seen.add(t)
            if t not in visited_src:
                stack.append(t)
    return seen


def _has_upstream_producer(graph: dict, nodes: dict, node_id: str) -> bool:
    """node_id 의 상류에 api_call/transform 생산자가 있으면 True
    (executor 가 상류 출력에서 동명 파라미터를 자동주입 → 입력 스키마에서 제외)."""
    radj: dict[str, list[str]] = {}
    for e in graph.get("edges", []):
        radj.setdefault(e["target"], []).append(e["source"])
    seen: set[str] = set()
    stack = list(radj.get(node_id, []))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        if (nodes.get(n) or {}).get("type") in ("api_call", "transform"):
            return True
        stack.extend(radj.get(n, []))
    return False


def _safe_name(s: str) -> str:
    """JSON Schema property/도구 인자 이름으로 안전화(영숫자·_ 만, 숫자 시작 금지)."""
    s = re.sub(r"[^A-Za-z0-9_]", "_", s or "")
    if not s:
        s = "param"
    if s[0].isdigit():
        s = "p_" + s
    return s


def _collect_input_params(graph: dict) -> list[dict]:
    """노출 대상 입력 파라미터 후보 목록.

    각 항목: {nid, loc, pname, type, description, required(bool)[, default]}.
    - 진입 노드: 상류에 api/transform 생산자가 없는 api 노드(자동주입 대상 하류는 제외).
    - 미표시(_input 아님) 파라미터는 정적값/엣지매핑으로 채워지면 제외.
    - 명시 입력(_input) 파라미터는 정적값·매핑이 있어도 노출하고 기존값을 default 로.
    """
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    starts = [n["id"] for n in graph.get("nodes", []) if n.get("type") == "start"]
    if starts:
        reachable = _forward_reachable(graph, starts)
        guaranteed = _guaranteed_reachable(graph, starts, nodes)
        candidates = [nid for nid in reachable
                      if (nodes.get(nid) or {}).get("type") == "api_call"]
    else:
        candidates = [n["id"] for n in graph.get("nodes", []) if n.get("type") == "api_call"]
        guaranteed = set(candidates)

    mapped: set = set()
    for e in graph.get("edges", []):
        tgt = e["target"]
        for m in (e.get("data_mapping") or []):
            nd = _norm_dest(m.get("to") or "")
            if nd:
                mapped.add((tgt, nd[0], nd[1]))

    items: list[dict] = []
    for nid in candidates:
        n = nodes.get(nid)
        if not n or n.get("operation_id") is None:
            continue
        if starts and _has_upstream_producer(graph, nodes, nid):
            continue
        op = specs_repo.get_operation(n["operation_id"])
        if not op:
            continue
        params = n.get("params") or {}
        for ps in (op.get("params_schema") or []):
            loc, pname = ps.get("in"), ps.get("name")
            if loc not in ("path", "query", "header"):
                continue
            existing = (params.get(loc) or {}).get(pname)
            is_mapped = (nid, loc, pname) in mapped
            sc = ps.get("schema") or {}
            t = sc.get("type") or "string"
            if t not in ("string", "integer", "number", "boolean"):
                t = "string"
            # 정책: 선언된 path/query/header 파라미터는 정적값 유무와 무관하게 항상 노출.
            #        정적값이 있으면 default 로만 제공(테스트값=기본값, 호출 시 override 가능).
            item = {
                "nid": nid, "loc": loc, "pname": pname, "type": t,
                "description": ps.get("description") or pname,
                "required": bool(ps.get("required") and nid in guaranteed and not is_mapped),
            }
            if existing not in (None, ""):
                item["default"] = existing   # 정적/테스트값 → 기본값(전달 없으면 이 값 사용)
                item["required"] = False       # 기본값 있으면 미전달 허용
            items.append(item)
    return items


def build_schema_and_alias(graph: dict) -> tuple[dict, dict]:
    """평면(사용자/LLM 친화) 인자 이름의 JSON Schema 와 별칭 맵을 함께 생성.

    - LangGraph 등 MCP 클라이언트가 'aptcd','dong' 같은 자연스러운 이름으로 인자를 채울 수 있도록
      파라미터명을 그대로 노출한다.
    - 같은 파라미터명이 여러 노드/위치에 있으면 '<nid>_<loc>_<pname>' 로 자동 구분.
    - alias[노출키] = '<nid>.<loc>.<pname>' → call_tool 이 실제 노드 파라미터로 되돌려 주입.
    """
    items = _collect_input_params(graph)
    counts: dict[str, int] = {}
    for it in items:
        counts[it["pname"]] = counts.get(it["pname"], 0) + 1

    props: dict = {}
    required: list[str] = []
    alias: dict = {}
    used: set = set()
    for it in items:
        base = it["pname"] if counts[it["pname"]] == 1 else f"{it['nid']}_{it['loc']}_{it['pname']}"
        key = _safe_name(base)
        k, i = key, 2
        while k in used:  # 안전장치: 그래도 충돌 시 접미사
            k, i = f"{key}_{i}", i + 1
        key = k
        used.add(key)
        prop = {"type": it["type"], "description": it["description"]}
        if "default" in it:
            prop["default"] = it["default"]
        props[key] = prop
        alias[key] = f"{it['nid']}.{it['loc']}.{it['pname']}"
        if it["required"] and "default" not in prop:
            required.append(key)
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema, alias


def build_input_schema(graph: dict) -> dict:
    """평면 인자 이름의 입력 JSON Schema (별칭은 build_schema_and_alias 참조)."""
    return build_schema_and_alias(graph)[0]


def apply_tool_args(graph: dict, args: dict) -> dict:
    """도구 인자를 deepcopy 그래프의 노드 params 에 주입."""
    g = copy.deepcopy(graph)
    nodes = {n["id"]: n for n in g.get("nodes", [])}
    for key, val in (args or {}).items():
        parts = key.split(".")
        if len(parts) >= 3:
            nid, loc, pname = parts[0], parts[1], ".".join(parts[2:])
            n = nodes.get(nid)
            if n is not None:
                n.setdefault("params", {}).setdefault(loc, {})[pname] = val
    return g


# ---------- 출력(응답) 스키마: $ref 해소 → Tool.outputSchema ----------
# call_tool 이 반환하는 실제 응답 페이로드(성공: 종단 오퍼레이션의 응답 본문 / dry_run·오류: 상태 객체)를
# LLM/에이전트가 미리 판단할 수 있도록 outputSchema 로 노출한다.
# 예약 응답 키: 성공 외 페이로드(dry_run·오류)에서 쓰는 키. outputSchema 최상위 속성과의
#   타입 충돌을 원천 차단하기 위해 최상위 properties 에서 제거(=자유 필드로 통과)한다.
_RESERVED_OUT_KEYS = {"dry_run", "status", "planned_actions", "preview", "note", "node", "error"}
_SPEC_SCHEMAS_CACHE: dict[int, dict] = {}  # spec_id -> components/schemas


def _spec_raw(spec_id):
    """스펙 원문(raw_content) 조회. get_spec_raw 가 있으면 사용, 없으면 DB 직접 조회.

    구버전 specs_repo(get_spec_raw 미존재)에서도 단일 파일 교체만으로 동작하도록 self-contained.
    """
    fn = getattr(specs_repo, "get_spec_raw", None)
    if fn is not None:
        try:
            return fn(spec_id)
        except Exception:
            pass
    try:
        from backend.db import connect
        conn = connect()
        try:
            row = conn.execute("SELECT raw_content FROM specs WHERE id=?", (spec_id,)).fetchone()
            if not row:
                return None
            try:
                return row["raw_content"]
            except Exception:
                return row[0]
        finally:
            conn.close()
    except Exception:
        return None


def _spec_schemas(spec_id) -> dict:
    """스펙 원문(raw_content)의 components/schemas 를 로드(캐시)."""
    if spec_id is None:
        return {}
    if spec_id in _SPEC_SCHEMAS_CACHE:
        return _SPEC_SCHEMAS_CACHE[spec_id]
    comps: dict = {}
    try:
        raw = _spec_raw(spec_id)
        if raw:
            comps = ((json.loads(raw).get("components") or {}).get("schemas")) or {}
    except Exception:
        comps = {}
    _SPEC_SCHEMAS_CACHE[spec_id] = comps
    return comps


def _resolve_refs(node, comps: dict, seen: frozenset = frozenset(), depth: int = 0):
    """OpenAPI $ref 를 components/schemas 로 재귀 인라인(순환·과도 깊이 방어)."""
    if depth > 12 or not isinstance(node, (dict, list)):
        return node
    if isinstance(node, list):
        return [_resolve_refs(x, comps, seen, depth + 1) for x in node]
    if "$ref" in node:
        name = str(node["$ref"]).split("/")[-1]
        if name in seen:  # 순환 → 참조만 남김
            return {"type": "object", "description": f"(순환 참조: {name})"}
        target = comps.get(name)
        if target is None:
            return {k: v for k, v in node.items() if k != "$ref"}
        return _resolve_refs(target, comps, seen | {name}, depth + 1)
    return {k: _resolve_refs(v, comps, seen, depth + 1) for k, v in node.items()}


def _relax_schema(node):
    """설명은 유지하되 검증이 응답을 막지 않도록 완화.

    - 모든 오브젝트에서 'required' 제거, additionalProperties=False → True
    - type/properties/items/description/enum 등 서술 정보는 보존(에이전트 판단용)
    """
    if isinstance(node, list):
        return [_relax_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out = {k: _relax_schema(v) for k, v in node.items() if k != "required"}
    if out.get("type") == "object" and out.get("additionalProperties") is False:
        out["additionalProperties"] = True
    return out


def _terminal_operation_id(graph: dict):
    """최종 응답(final)을 만드는 종단 api_call 노드의 operation_id.

    executor 는 end 노드(없으면 마지막 성공 노드) 출력을 final 로 반환하므로,
    end 로부터 역방향으로 가장 가까운 api_call 오퍼레이션을 택한다.
    """
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    preds: dict = {}
    for e in graph.get("edges", []):
        preds.setdefault(e.get("target"), []).append(e.get("source"))
    end_ids = [nid for nid, n in nodes.items() if n.get("type") == "end"]
    seen, queue = set(), list(end_ids)
    while queue:
        cur = queue.pop(0)
        for p in preds.get(cur, []):
            if p in seen:
                continue
            seen.add(p)
            n = nodes.get(p)
            if n and n.get("type") == "api_call" and n.get("operation_id") is not None:
                return n["operation_id"]
            queue.append(p)
    api = [n for n in nodes.values()
           if n.get("type") == "api_call" and n.get("operation_id") is not None]
    return api[-1]["operation_id"] if api else None


_FALLBACK_OUTPUT_SCHEMA = {
    "type": "object",
    "description": "응답 구조가 스펙에 정의되지 않았습니다(임의 객체). 실제 응답 본문이 그대로 반환됩니다.",
    "additionalProperties": True,
}


def build_output_schema(graph: dict):
    """종단 오퍼레이션의 응답 스키마를 $ref 해소·완화해 outputSchema 로 생성.

    항상 JSON Schema(object)를 반환한다(응답 스키마가 없거나 해소 불가하면 허용형 폴백).
    검증 안전: 성공(응답 본문)·dry_run·오류 페이로드가 모두 통과하도록 완화한다.
    """
    opid = _terminal_operation_id(graph)
    if opid is None:
        return dict(_FALLBACK_OUTPUT_SCHEMA)
    try:
        op = specs_repo.get_operation(opid)
    except Exception:
        op = None
    if not op:
        return dict(_FALLBACK_OUTPUT_SCHEMA)
    rs = op.get("response_schema")
    if not isinstance(rs, dict) or not rs:
        return dict(_FALLBACK_OUTPUT_SCHEMA)
    resolved = _resolve_refs(rs, _spec_schemas(op.get("spec_id")))
    if not isinstance(resolved, dict) or not resolved:
        return dict(_FALLBACK_OUTPUT_SCHEMA)
    schema = _relax_schema(resolved)
    if schema.get("type") != "object":
        # 비오브젝트 응답은 result 로 래핑(outputSchema 는 object 여야 안전)
        schema = {"type": "object", "properties": {"result": schema}}
    schema.setdefault("additionalProperties", True)
    props = schema.get("properties")
    if isinstance(props, dict):
        for k in list(props):
            if k in _RESERVED_OUT_KEYS:  # dry_run/오류 키와의 타입 충돌 방지
                props.pop(k, None)
    return schema


def build_tools() -> None:
    _TOOLS.clear()
    _SPEC_SCHEMAS_CACHE.clear()
    for w in load_exposed_workflows():
        graph = wf_repo.get_graph(w["id"])
        if graph is None:
            continue
        tname = build_tool_name(w["id"], w["name"], w.get("mcp_tool_name"))
        schema, alias = build_schema_and_alias(graph)
        # dry-run 인자 노출: true 면 변경성 호출을 실행하지 않고 실행 계획만 반환
        schema.setdefault("properties", {})["dry_run"] = {
            "type": "boolean",
            "description": "true 이면 변경(POST/PUT/DELETE/PATCH) 호출을 실행하지 않고 실행 계획(planned_actions)만 반환합니다. 먼저 dry_run=true 로 계획을 확인한 뒤, 사용자 승인 시 dry_run 없이(또는 false) 다시 호출해 실제 실행하세요.",
        }
        _TOOLS[tname] = {
            "wf": w,
            "graph": graph,
            "schema": schema,
            "alias": alias,  # 노출키(평면) → '<nid>.<loc>.<pname>'
            "output_schema": build_output_schema(graph),  # Tool.outputSchema (항상 존재)
        }


def ensure_tools(force: bool = False) -> bool:
    """노출 워크플로우 변경 시그니처를 확인해 바뀐 경우(또는 force)에만 재빌드.

    반환: 재빌드했으면 True(=목록 변경됨). 변경 없으면 False(가벼운 1쿼리만 수행).
    """
    global _TOOLS_SIG
    try:
        sig = wf_repo.change_signature(MCP_GROUP)
    except Exception:
        sig = None
    if not force and _TOOLS and sig is not None and sig == _TOOLS_SIG:
        return False
    build_tools()
    _TOOLS_SIG = sig
    return True


async def _poll_changes() -> None:
    """주기적으로 변경을 감지해 지원 클라이언트에 tools/list_changed 알림.

    list 호출이 없어도 이미 연결된 클라이언트가 재시작 없이 갱신되도록 함.
    세션이 아직 없거나 알림 전송이 실패해도(클라이언트 미지원 등) 조용히 무시.
    """
    while True:
        await asyncio.sleep(POLL_SECS)
        try:
            if ensure_tools() and _SESSION is not None:
                await _SESSION.send_tool_list_changed()
        except Exception:
            pass


# ---------- MCP 핸들러 ----------
@server.list_tools()
async def list_tools() -> list[types.Tool]:
    global _SESSION
    ensure_tools()  # 변경 시그니처 확인 → 바뀐 경우에만 재빌드(가벼움)
    try:  # 백그라운드 알림에 쓸 현재 세션 캡처
        _SESSION = server.request_context.session
    except Exception:
        pass
    tools: list[types.Tool] = []
    supports_output = "outputSchema" in types.Tool.model_fields
    for tname, info in _TOOLS.items():
        kwargs = dict(
            name=tname,
            description=(info["wf"].get("description") or info["wf"]["name"]),
            inputSchema=info["schema"],
        )
        out = info.get("output_schema")
        if out and supports_output:  # 구버전 SDK 호환: 필드 있을 때만 부착
            kwargs["outputSchema"] = out
        tools.append(types.Tool(**kwargs))
    return tools


@server.call_tool()
async def call_tool(name: str, arguments: dict | None):
    info = _TOOLS.get(name)
    if info is None:
        return [types.TextContent(type="text", text=f"알 수 없는 도구: {name}")]
    args = dict(arguments or {})
    # 예약 인자 dry_run 은 그래프 파라미터로 주입하지 않고 실행 모드로만 사용
    dry_run = bool(args.pop("dry_run", False))
    # 평면 인자 이름(aptcd, dong ...) → 실제 노드 파라미터 키('<nid>.<loc>.<pname>') 로 되돌림.
    # 별칭에 없는 키(노드 스코프 키 직접 전달 등)는 그대로 통과.
    alias = info.get("alias") or {}
    resolved = {alias.get(k, k): v for k, v in args.items()}
    graph = apply_tool_args(info["graph"], resolved)
    result = executor.run_workflow(
        graph,
        initial_input=args,
        auth=None,
        operation_resolver=specs_repo.get_operation,
        dry_run=dry_run,
    )
    try:
        exec_repo.save(result, source="mcp-dryrun" if dry_run else "mcp", tool_name=name)  # 감사 로그
    except Exception:
        pass
    if dry_run:
        payload = {
            "dry_run": True,
            "status": result.get("status"),
            "planned_actions": result.get("planned_actions", []),
            "preview": result.get("final"),
            "note": "실행되지 않았습니다. planned_actions 를 사용자에게 보여주고 승인받은 뒤 dry_run 없이 다시 호출하세요.",
        }
    elif result.get("status") == "success":
        payload = result.get("final")
    else:
        failed = next((l for l in result.get("logs", []) if l.get("status") == "failed"), None)
        payload = {
            "status": "failed",
            "node": failed.get("node_key") if failed else None,
            "error": failed.get("error") if failed else None,
        }
    # content(텍스트)는 기존과 동일(하위호환). outputSchema 검증·구조화 소비를 위해
    # structuredContent 도 함께 반환(dict 가 아니면 result 로 래핑).
    content = [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]
    structured = payload if isinstance(payload, dict) else {"result": payload}
    return content, structured


async def main() -> None:
    init_db()
    ensure_tools(force=True)  # 기동 시 1회 빌드 + 시그니처 기록
    init_opts = server.create_initialization_options(
        # tools/list_changed 알림 capability 광고 → 지원 클라이언트가 자동 갱신
        notification_options=NotificationOptions(tools_changed=True),
    )
    async with stdio_server() as (read_stream, write_stream):
        poller = asyncio.create_task(_poll_changes()) if POLL_SECS > 0 else None
        try:
            await server.run(read_stream, write_stream, init_opts)
        finally:
            if poller is not None:
                poller.cancel()


if __name__ == "__main__":
    asyncio.run(main())
