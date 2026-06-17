"""MCP 서버 (stdio) — mcp_exposed=1 워크플로우를 외부 MCP 클라이언트(Claude Desktop 등)에 도구로 노출.

실행:  PYTHONPATH=<repo> python -m backend.mcp_server
  - MCP_GROUP 환경변수가 있으면 해당 그룹 워크플로우만 노출.
  - 도구 목록은 서버 기동 시 1회 생성 → 노출/그룹/이름/그래프 변경 후 클라이언트 재시작 필요.
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
from engine import executor

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

MCP_GROUP = os.environ.get("MCP_GROUP")
SERVER_NAME = os.environ.get("MCP_SERVER_NAME") or ("mcp-" + MCP_GROUP if MCP_GROUP else "mcp-provider")

server = Server(SERVER_NAME)
_TOOLS: dict[str, dict] = {}  # tool_name -> {"wf":..., "graph":..., "schema":...}


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


def build_input_schema(graph: dict) -> dict:
    """시작 노드에 연결된 api 노드의 '미충족 필수 파라미터'를 JSON Schema 로.
    키: '<node_key>.<location>.<param>' (apply_tool_args 와 동일 규약)."""
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    starts = [n["id"] for n in graph.get("nodes", []) if n.get("type") == "start"]
    targets = {e["target"] for e in graph.get("edges", []) if e["source"] in starts}
    candidates = targets if targets else [
        n["id"] for n in graph.get("nodes", []) if n.get("type") == "api_call"
    ]
    props: dict = {}
    required: list[str] = []
    for nid in candidates:
        n = nodes.get(nid)
        if not n or n.get("type") != "api_call" or n.get("operation_id") is None:
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
            sc = ps.get("schema") or {}
            key = f"{nid}.{loc}.{pname}"
            t = sc.get("type") or "string"
            if t not in ("string", "integer", "number", "boolean"):
                t = "string"
            props[key] = {"type": t, "description": ps.get("description") or pname}
            if ps.get("required"):
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
        _TOOLS[tname] = {
            "wf": w,
            "graph": graph,
            "schema": build_input_schema(graph),
        }


# ---------- MCP 핸들러 ----------
@server.list_tools()
async def list_tools() -> list[types.Tool]:
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
    args = arguments or {}
    graph = apply_tool_args(info["graph"], args)
    result = executor.run_workflow(
        graph,
        initial_input=args,
        auth=None,
        operation_resolver=specs_repo.get_operation,
    )
    return [types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


async def main() -> None:
    init_db()
    build_tools()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
