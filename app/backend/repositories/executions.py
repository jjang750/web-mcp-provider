"""executions / execution_logs 리포지토리."""
from __future__ import annotations

import json
from typing import Any, Optional

from backend.db import connect


def _dumps(v: Any) -> Optional[str]:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _loads(v: Optional[str], default: Any = None) -> Any:
    if v is None or v == "":
        return default
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return default


def save(result: dict, source: str = "web", tool_name: Optional[str] = None) -> int:
    """ExecutionResult(dict)를 저장하고 execution_id 를 반환. source: web|mcp."""
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO executions (workflow_id, status, started_at, finished_at, result, source, tool_name) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                result.get("workflow_id"), result.get("status"),
                result.get("started_at"), result.get("finished_at"),
                _dumps(result.get("result")), source, tool_name,
            ),
        )
        exec_id = cur.lastrowid
        for log in result.get("logs", []):
            conn.execute(
                "INSERT INTO execution_logs "
                "(execution_id, node_key, seq, status, input, output, error, timestamp) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    exec_id, log.get("node_key"), log.get("seq"), log.get("status"),
                    _dumps(log.get("input")), _dumps(log.get("output")),
                    log.get("error"), log.get("timestamp"),
                ),
            )
        conn.commit()
        return exec_id
    finally:
        conn.close()


def _filter_clause(source: Optional[str], q: Optional[str]) -> tuple[str, list]:
    """source/검색어(q)에 대한 WHERE 절과 파라미터. q 는 워크플로우명/도구명/상태/실행ID LIKE."""
    clauses: list[str] = []
    params: list = []
    if source == "web":
        clauses.append("(e.source = 'web' OR e.source IS NULL)")  # 레거시(컬럼 추가 전) 실행은 웹으로 간주
    elif source:
        clauses.append("e.source = ?")
        params.append(source)
    if q:
        like = f"%{q.strip()}%"
        clauses.append(
            "(w.name LIKE ? OR e.tool_name LIKE ? OR e.status LIKE ? OR CAST(e.id AS TEXT) LIKE ?)"
        )
        params += [like, like, like, like]
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def list_recent(limit: int = 100, offset: int = 0,
                source: Optional[str] = None, q: Optional[str] = None) -> list[dict]:
    """감사 로그용 실행 목록(워크플로우명 포함). source 필터·q 검색·offset 페이징 지원."""
    conn = connect()
    try:
        where, params = _filter_clause(source, q)
        sql = ("SELECT e.id, e.workflow_id, e.status, e.started_at, e.finished_at, "
               "e.source, e.tool_name, w.name AS wf_name "
               "FROM executions e LEFT JOIN workflows w ON e.workflow_id = w.id"
               + where + " ORDER BY e.id DESC LIMIT ? OFFSET ?")
        rows = conn.execute(sql, params + [limit, offset]).fetchall()
        out = []
        for r in rows:
            keys = r.keys()
            out.append({
                "execution_id": r["id"],
                "workflow_id": r["workflow_id"],
                "workflow_name": r["wf_name"],
                "status": r["status"],
                "started_at": r["started_at"],
                "finished_at": r["finished_at"],
                "source": r["source"] if "source" in keys else None,
                "tool_name": r["tool_name"] if "tool_name" in keys else None,
            })
        return out
    finally:
        conn.close()


def count_recent(source: Optional[str] = None, q: Optional[str] = None) -> int:
    """source 필터·q 검색에 해당하는 실행 총 건수(페이징 메타용)."""
    conn = connect()
    try:
        where, params = _filter_clause(source, q)
        sql = ("SELECT COUNT(*) AS c FROM executions e "
               "LEFT JOIN workflows w ON e.workflow_id = w.id" + where)
        row = conn.execute(sql, params).fetchone()
        return int(row["c"]) if row else 0
    finally:
        conn.close()


def get(exec_id: int) -> Optional[dict]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM executions WHERE id=?", (exec_id,)).fetchone()
        if not row:
            return None
        keys = row.keys()
        logs = conn.execute(
            "SELECT * FROM execution_logs WHERE execution_id=? ORDER BY seq", (exec_id,)
        ).fetchall()
        return {
            "execution_id": row["id"],
            "workflow_id": row["workflow_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "source": row["source"] if "source" in keys else None,
            "tool_name": row["tool_name"] if "tool_name" in keys else None,
            "result": _loads(row["result"]),
            "logs": [
                {
                    "node_key": l["node_key"],
                    "seq": l["seq"],
                    "status": l["status"],
                    "input": _loads(l["input"]),
                    "output": _loads(l["output"]),
                    "error": l["error"],
                    "timestamp": l["timestamp"],
                }
                for l in logs
            ],
        }
    finally:
        conn.close()
