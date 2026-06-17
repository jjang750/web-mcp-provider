"""그래프 검증 / 토폴로지 정렬 / 순차 실행 / 노드별 로그 (사양서 §4).

- 그래프 검증: 사이클 거부.
- 노드 실패 시 raise 안 함 → 해당 노드 failed, 이후(하류) 노드 skipped.
- start 출력 = initial_input ($). 엣지 data_mapping($.x → params.path.x)로 상류 출력 주입.
- base_url 우선순위: node.base_url → operation.base_url → DEFAULT_BASE_URL.
- JSONPath 부분집합: $, 점 접근($.a.b), 인덱스($.a[0].b).
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from engine import http_client

OperationResolver = Callable[[int], Optional[dict]]
NodeEventCb = Callable[[dict], None]

_TOKEN_RE = re.compile(r"([A-Za-z_][\w-]*)|\[(\d+)\]")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- JSONPath 부분집합 ----------
def get_by_path(data: Any, path: str) -> Any:
    """'$', '$.a.b', '$.a[0].b' 지원. 미존재 시 None."""
    if path in ("$", "", None):
        return data
    p = path[2:] if path.startswith("$.") else (path[1:] if path.startswith("$") else path)
    cur = data
    for name, idx in _TOKEN_RE.findall(p):
        if name:
            if isinstance(cur, dict) and name in cur:
                cur = cur[name]
            else:
                return None
        elif idx != "":
            i = int(idx)
            if isinstance(cur, list) and 0 <= i < len(cur):
                cur = cur[i]
            else:
                return None
    return cur


def set_by_path(params: dict, dest: str, value: Any) -> None:
    """'params.path.x' / 'path.x' / 'query.y' / 'body.z' 형태에 값 주입."""
    dest = dest.strip()
    if dest.startswith("$."):
        dest = dest[2:]
    parts = [seg for seg in dest.split(".") if seg]
    if parts and parts[0] == "params":
        parts = parts[1:]
    if not parts:
        return
    cur = params
    for seg in parts[:-1]:
        nxt = cur.get(seg)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[seg] = nxt
        cur = nxt
    cur[parts[-1]] = value


# ---------- 그래프 헬퍼 ----------
def _node_map(graph: dict) -> dict[str, dict]:
    return {n["id"]: n for n in graph.get("nodes", [])}


def _adjacency(graph: dict) -> tuple[dict[str, list[str]], dict[str, int]]:
    adj: dict[str, list[str]] = {n["id"]: [] for n in graph.get("nodes", [])}
    indeg: dict[str, int] = {n["id"]: 0 for n in graph.get("nodes", [])}
    for e in graph.get("edges", []):
        s, t = e["source"], e["target"]
        if s in adj and t in indeg:
            adj[s].append(t)
            indeg[t] += 1
    return adj, indeg


def topological_order(graph: dict) -> list[str]:
    """Kahn 알고리즘. 사이클이면 ValueError."""
    adj, indeg = _adjacency(graph)
    queue = [n for n, d in indeg.items() if d == 0]
    order: list[str] = []
    indeg = dict(indeg)
    while queue:
        queue.sort()  # 결정적 순서
        n = queue.pop(0)
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                queue.append(m)
    if len(order) != len(indeg):
        raise ValueError("워크플로우 그래프에 사이클이 있어 실행할 수 없습니다.")
    return order


def validate_graph(graph: dict) -> None:
    nodes = _node_map(graph)
    for e in graph.get("edges", []):
        if e["source"] not in nodes:
            raise ValueError(f"엣지 source 노드를 찾을 수 없습니다: {e['source']}")
        if e["target"] not in nodes:
            raise ValueError(f"엣지 target 노드를 찾을 수 없습니다: {e['target']}")
    topological_order(graph)  # 사이클 검증


def _incoming_edges(graph: dict, node_id: str) -> list[dict]:
    return [e for e in graph.get("edges", []) if e["target"] == node_id]


def _descendants(graph: dict, start: str) -> set[str]:
    adj, _ = _adjacency(graph)
    seen: set[str] = set()
    stack = list(adj.get(start, []))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adj.get(n, []))
    return seen


# ---------- 실행 ----------
def run_workflow(
    graph: dict,
    initial_input: Any = None,
    auth: Optional[dict] = None,
    on_node_event: Optional[NodeEventCb] = None,
    *,
    operation_resolver: OperationResolver,
    timeout: float = 30.0,
    default_base_url: str = http_client.DEFAULT_BASE_URL,
) -> dict:
    """그래프를 검증·토폴로지 정렬 후 순차 실행. ExecutionResult(dict) 반환."""
    validate_graph(graph)
    order = topological_order(graph)
    nodes = _node_map(graph)

    outputs: dict[str, Any] = {}
    logs: list[dict] = []
    skipped: set[str] = set()
    overall_failed = False
    started_at = _now()

    def emit(payload: dict) -> None:
        if on_node_event:
            try:
                on_node_event(payload)
            except Exception:
                pass

    for seq, node_id in enumerate(order):
        node = nodes[node_id]
        ntype = node.get("type", "api_call")

        if node_id in skipped:
            log = {"node_key": node_id, "seq": seq, "status": "skipped",
                   "input": None, "output": None, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        # 상류 출력으로 입력 구성
        node_input: Any = None
        if ntype == "start":
            node_input = initial_input
            outputs[node_id] = initial_input
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": initial_input, "output": initial_input, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        # api_call / transform / end: 정적 params + 엣지 매핑 주입
        params = copy.deepcopy(node.get("params") or {})
        for ed in _incoming_edges(graph, node_id):
            src_out = outputs.get(ed["source"])
            for m in ed.get("data_mapping", []) or []:
                frm = m.get("from") or m.get("from_")
                to = m.get("to")
                if frm and to:
                    set_by_path(params, to, get_by_path(src_out, frm))
        node_input = params

        if ntype == "end":
            merged = {e["source"]: outputs.get(e["source"]) for e in _incoming_edges(graph, node_id)}
            outputs[node_id] = merged or initial_input
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": node_input, "output": outputs[node_id], "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        if ntype == "transform":
            outputs[node_id] = params
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": node_input, "output": params, "error": None, "timestamp": _now()}
            logs.append(log)
            emit(log)
            continue

        # api_call
        op = None
        op_id = node.get("operation_id")
        if op_id is not None:
            op = operation_resolver(op_id)
        if not op:
            overall_failed = True
            err = f"오퍼레이션을 찾을 수 없습니다 (operation_id={op_id})."
            log = {"node_key": node_id, "seq": seq, "status": "failed",
                   "input": node_input, "output": None, "error": err, "timestamp": _now()}
            logs.append(log)
            emit(log)
            skipped |= _descendants(graph, node_id)
            continue

        base_url = http_client.resolve_base_url(
            node.get("base_url"), op.get("base_url"), default_base_url
        )
        try:
            result = http_client.call(
                op["method"],
                base_url,
                op["path"],
                path_params=params.get("path"),
                query=params.get("query"),
                header=params.get("header"),
                body=params.get("body"),
                auth=auth,
                timeout=timeout,
            )
            status_code = result.get("status_code", 0)
            if status_code >= 400:
                overall_failed = True
                err = f"HTTP {status_code}"
                log = {"node_key": node_id, "seq": seq, "status": "failed",
                       "input": node_input, "output": result, "error": err, "timestamp": _now()}
                logs.append(log)
                emit(log)
                skipped |= _descendants(graph, node_id)
                continue
            outputs[node_id] = result.get("body")
            log = {"node_key": node_id, "seq": seq, "status": "success",
                   "input": node_input, "output": result.get("body"),
                   "error": None, "timestamp": _now(), "status_code": status_code}
            logs.append(log)
            emit(log)
        except Exception as exc:  # 네트워크/프로토콜 오류 등 — raise 하지 않음
            overall_failed = True
            log = {"node_key": node_id, "seq": seq, "status": "failed",
                   "input": node_input, "output": None, "error": str(exc), "timestamp": _now()}
            logs.append(log)
            emit(log)
            skipped |= _descendants(graph, node_id)

    return {
        "execution_id": None,
        "workflow_id": graph.get("workflow_id"),
        "status": "failed" if overall_failed else "success",
        "started_at": started_at,
        "finished_at": _now(),
        "result": outputs,
        "logs": logs,
    }
