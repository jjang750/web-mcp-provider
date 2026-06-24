"""workflows / nodes / edges 리포지토리.

와이어 모델(Node/Edge) ↔ DB 행 변환. 엣지 data_mapping 키는 "from"/"to" 고정.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from backend.db import connect
from engine.http_client import DEFAULT_BASE_URL, build_url


def _dumps(v: Any) -> Optional[str]:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _loads(v: Optional[str], default: Any = None) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return default


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------- 워크플로우 ----------
def create(name: str, description: Optional[str] = None) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO workflows (name, description, created_at, updated_at) VALUES (?,?,?,?)",
            (name, description, _now(), _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def list_all() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, name, description, mcp_exposed, mcp_group, mcp_tool_name, updated_at "
            "FROM workflows ORDER BY id DESC"
        ).fetchall()
        out = []
        for r in rows:
            s = _summary(r)
            s["node_count"] = conn.execute(
                "SELECT COUNT(*) AS c FROM nodes WHERE workflow_id=?", (r["id"],)
            ).fetchone()["c"]
            ms = conn.execute(
                "SELECT DISTINCT LOWER(o.method) AS m FROM nodes n "
                "JOIN operations o ON n.operation_id = o.id WHERE n.workflow_id=?",
                (r["id"],),
            ).fetchall()
            s["methods"] = [x["m"] for x in ms if x["m"]]
            ep_rows = conn.execute(
                "SELECT o.method AS method, o.path AS path, "
                "n.base_url AS node_base, o.base_url AS op_base "
                "FROM nodes n JOIN operations o ON n.operation_id = o.id "
                "WHERE n.workflow_id=? AND o.path IS NOT NULL ORDER BY n.id",
                (r["id"],),
            ).fetchall()
            s["endpoints"] = _endpoints(ep_rows)
            out.append(s)
        return out
    finally:
        conn.close()


def _endpoints(rows) -> list[dict]:
    """노드별 호출 대상 엔드포인트. base_url 우선순위는 executor와 동일(node→op→DEFAULT)."""
    out, seen = [], set()
    for r in rows:
        base = r["node_base"] or r["op_base"] or DEFAULT_BASE_URL
        path = r["path"] or ""
        try:
            url = build_url(base, path)
        except Exception:
            url = (base.rstrip("/") + "/" + path.lstrip("/")) if base else path
        method = (r["method"] or "GET").upper()
        key = (method, url)
        if key in seen:
            continue
        seen.add(key)
        out.append({"method": method, "path": path, "url": url})
    return out


def _summary(row) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "mcp_exposed": bool(row["mcp_exposed"]),
        "mcp_group": row["mcp_group"],
        "mcp_tool_name": row["mcp_tool_name"],
        "updated_at": row["updated_at"],
    }


def _node_row_to_wire(row) -> dict:
    return {
        "id": row["node_key"],
        "type": row["type"] or "api_call",
        "label": row["label"],
        "operation_id": row["operation_id"],
        "base_url": row["base_url"],
        "params": _loads(row["params"], {}) or {},
        "position": {"x": row["position_x"] or 0, "y": row["position_y"] or 0},
    }


def _edge_row_to_wire(row) -> dict:
    keys = row.keys()
    return {
        "id": row["edge_key"],
        "source": row["source_node_key"],
        "target": row["target_node_key"],
        "data_mapping": _loads(row["data_mapping"], []) or [],
        "label": row["label"] if "label" in keys else None,
    }


def get_detail(workflow_id: int) -> Optional[dict]:
    conn = connect()
    try:
        wf = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        if not wf:
            return None
        nodes = conn.execute(
            "SELECT * FROM nodes WHERE workflow_id=? ORDER BY id", (workflow_id,)
        ).fetchall()
        edges = conn.execute(
            "SELECT * FROM edges WHERE workflow_id=? ORDER BY id", (workflow_id,)
        ).fetchall()
        detail = _summary(wf)
        detail["nodes"] = [_node_row_to_wire(n) for n in nodes]
        detail["edges"] = [_edge_row_to_wire(e) for e in edges]
        return detail
    finally:
        conn.close()


def get_graph(workflow_id: int) -> Optional[dict]:
    """executor 입력용 그래프."""
    detail = get_detail(workflow_id)
    if detail is None:
        return None
    return {
        "workflow_id": workflow_id,
        "nodes": detail["nodes"],
        "edges": detail["edges"],
    }


def update(
    workflow_id: int,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    nodes: Optional[list[dict]] = None,
    edges: Optional[list[dict]] = None,
) -> Optional[dict]:
    conn = connect()
    try:
        wf = conn.execute("SELECT id FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        if not wf:
            # 없으면 해당 id 로 생성(upsert) — 에디터에서 /editor/{id} 로 바로 저장 가능하게
            conn.execute(
                "INSERT INTO workflows (id, name, description, created_at, updated_at) VALUES (?,?,?,?,?)",
                (workflow_id, name or ("워크플로우 #" + str(workflow_id)), description, _now(), _now()),
            )
        if name is not None:
            conn.execute("UPDATE workflows SET name=? WHERE id=?", (name, workflow_id))
        if description is not None:
            conn.execute("UPDATE workflows SET description=? WHERE id=?", (description, workflow_id))

        if nodes is not None:
            conn.execute("DELETE FROM nodes WHERE workflow_id=?", (workflow_id,))
            for n in nodes:
                pos = n.get("position") or {}
                conn.execute(
                    "INSERT INTO nodes (workflow_id, node_key, operation_id, type, label, base_url, params, position_x, position_y) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        workflow_id, n["id"], n.get("operation_id"),
                        n.get("type", "api_call"), n.get("label"), n.get("base_url"),
                        _dumps(n.get("params") or {}),
                        pos.get("x", 0), pos.get("y", 0),
                    ),
                )
        if edges is not None:
            conn.execute("DELETE FROM edges WHERE workflow_id=?", (workflow_id,))
            for e in edges:
                conn.execute(
                    "INSERT INTO edges (workflow_id, edge_key, source_node_key, target_node_key, data_mapping, label) "
                    "VALUES (?,?,?,?,?,?)",
                    (
                        workflow_id, e["id"], e["source"], e["target"],
                        _dumps(e.get("data_mapping") or []),
                        e.get("label"),
                    ),
                )
        conn.execute("UPDATE workflows SET updated_at=? WHERE id=?", (_now(), workflow_id))
        conn.commit()
    finally:
        conn.close()
    return get_detail(workflow_id)


def delete(workflow_id: int) -> bool:
    conn = connect()
    try:
        cur = conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def set_expose(
    workflow_id: int, exposed: bool, group: Optional[str], tool_name: Optional[str]
) -> Optional[dict]:
    conn = connect()
    try:
        wf = conn.execute("SELECT id FROM workflows WHERE id=?", (workflow_id,)).fetchone()
        if not wf:
            return None
        conn.execute(
            "UPDATE workflows SET mcp_exposed=?, mcp_group=?, mcp_tool_name=?, updated_at=? WHERE id=?",
            (1 if exposed else 0, group, tool_name, _now(), workflow_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT mcp_exposed, mcp_group, mcp_tool_name FROM workflows WHERE id=?", (workflow_id,)
        ).fetchone()
        return {
            "mcp_exposed": bool(row["mcp_exposed"]),
            "mcp_group": row["mcp_group"],
            "mcp_tool_name": row["mcp_tool_name"],
        }
    finally:
        conn.close()
