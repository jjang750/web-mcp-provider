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


def build_input_schema(graph: dict) -> dict:
    """start 에서 전방 도달 가능한 '진입 api 노드'의 미충족 파라미터를 JSON Schema 로.

    - 진입 노드: 상류에 api/transform 생산자가 없는 api 노드(자동주입 대상 하류 노드는 제외).
    - 정적값/엣지 data_mapping 으로 이미 채워진 파라미터는 제외.
    - required: 분기(condition/switch/filter)를 거치지 않고 무조건 도달하는 노드의 필수 파라미터만
      (분기 하위 노드는 실행 여부가 런타임 의존 → properties 에는 노출하되 required 에서 제외).
    - 키: '<node_id>.<location>.<param>' (apply_tool_args 와 동일 규약).
    """
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    starts = [n["id"] for n in graph.get("nodes", []) if n.get("type") == "start"]
    if starts:
        reachable = _forward_reachable(graph, starts)
        guaranteed = _guaranteed_reachable(graph, starts, nodes)
        candidates = [nid for nid in reachable
                      if (nodes.get(nid) or {}).get("type") == "api_call"]
    else:
        # start 노드 없음: 모든 api 노드를 후보로, 전부 required 후보(하위호환)
        candidates = [n["id"] for n in graph.get("nodes", []) if n.get("type") == "api_call"]
        guaranteed = set(candidates)

    # 엣지 data_mapping 으로 채워지는 (node_id, loc, pname) 집합
    mapped: set = set()
    for e in graph.get("edges", []):
        tgt = e["target"]
        for m in (e.get("data_mapping") or []):
            nd = _norm_dest(m.get("to") or "")
            if nd:
                mapped.add((tgt, nd[0], nd[1]))

    props: dict = {}
    required: list[str] = []
    for nid in candidates:
        n = nodes.get(nid)
        if not n or n.get("operation_id") is None:
            continue
        # 진입 노드만(상류 생산자가 있으면 executor 가 자동주입 → 스키마 제외)
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
            if existing not in (None, ""):
                continue  # 정적값으로 이미 채워짐
            if (nid, loc, pname) in mapped:
                continue  # 엣지 매핑으로 채워짐
            sc = ps.get("schema") or {}
            key = f"{nid}.{loc}.{pname}"
            t = sc.get("type") or "string"
            if t not in ("string", "integer", "number", "boolean"):
                t = "string"
            props[key] = {"type": t, "description": ps.get("description") or pname}
            if ps.get("required") and nid in guaranteed:
                required.append(key)
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema


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


def build_tools() -> None:
    _TOOLS.clear()
    for w in load_exposed_workflows():
        graph = wf_repo.get_graph(w["id"])
        if graph is None:
            continue
        tname = build_tool_name(w["id"], w["name"], w.get("mcp_tool_name"))
        schema = build_input_schema(graph)
        # dry-run 인자 노출: true 면 변경성 호출을 실행하지 않고 실행 계획만 반환
        schema.setdefault("properties", {})["dry_run"] = {
            "type": "boolean",
            "description": "true 이면 변경(POST/PUT/DELETE/PATCH) 호출을 실행하지 않고 실행 계획(planned_actions)만 반환합니다. 먼저 dry_run=true 로 계획을 확인한 뒤, 사용자 승인 시 dry_run 없이(또는 false) 다시 호출해 실제 실행하세요.",
        }
        _TOOLS[tname] = {
            "wf": w,
            "graph": graph,
            "schema": schema,
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
    return [
        types.Tool(
            name=tname,
            description=(info["wf"].get("description") or info["wf"]["name"]),
            inputSchema=info["schema"],
        )
        for tname, info in _TOOLS.items()
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict | None) -> list[types.TextContent]:
    info = _TOOLS.get(name)
    if info is None:
        return [types.TextContent(type="text", text=f"알 수 없는 도구: {name}")]
    args = dict(arguments or {})
    # 예약 인자 dry_run 은 그래프 파라미터로 주입하지 않고 실행 모드로만 사용
    dry_run = bool(args.pop("dry_run", False))
    graph = apply_tool_args(info["graph"], args)
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
    return [types.TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


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
