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


def save(result: dict) -> int:
    """ExecutionResult(dict)를 저장하고 execution_id 를 반환·주입."""
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO executions (workflow_id, status, started_at, finished_at, result) "
            "VALUES (?,?,?,?,?)",
            (
                result.get("workflow_id"), result.get("status"),
                result.get("started_at"), result.get("finished_at"),
                _dumps(result.get("result")),
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


def get(exec_id: int) -> Optional[dict]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM executions WHERE id=?", (exec_id,)).fetchone()
        if not row:
            return None
        logs = conn.execute(
            "SELECT * FROM execution_logs WHERE execution_id=? ORDER BY seq", (exec_id,)
        ).fetchall()
        return {
            "execution_id": row["id"],
            "workflow_id": row["workflow_id"],
            "status": row["status"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
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
