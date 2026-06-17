"""specs / operations 리포지토리 (SQLite CRUD).

JSON 컬럼(params_schema/request_schema/response_schema/auth)은 TEXT(json.dumps)로 저장.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from backend.db import connect


def _dumps(v: Any) -> Optional[str]:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _loads(v: Optional[str]) -> Any:
    if v is None or v == "":
        return None
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return v


def create_spec_with_operations(
    name: str,
    source_type: str,
    source_ref: Optional[str],
    raw_content: str,
    parse_result,
) -> dict:
    """스펙 + 파싱된 오퍼레이션을 저장하고 요약을 반환."""
    now = datetime.now(timezone.utc).isoformat()
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO specs (name, source_type, source_ref, spec_version, raw_content, parsed_at) "
            "VALUES (?,?,?,?,?,?)",
            (name, source_type, source_ref, parse_result.spec_version, raw_content, now),
        )
        spec_id = cur.lastrowid
        for op in parse_result.operations:
            conn.execute(
                "INSERT INTO operations "
                "(spec_id, operation_id, method, path, base_url, summary, params_schema, request_schema, response_schema, auth) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    spec_id, op.operation_id, op.method, op.path, op.base_url, op.summary,
                    _dumps(op.params_schema), _dumps(op.request_schema),
                    _dumps(op.response_schema), _dumps(op.auth),
                ),
            )
        conn.commit()
        return {
            "spec_id": spec_id,
            "name": name,
            "spec_version": parse_result.spec_version,
            "base_url": parse_result.base_url,
            "operation_count": len(parse_result.operations),
            "warnings": list(parse_result.warnings),
        }
    finally:
        conn.close()


def _op_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "spec_id": row["spec_id"],
        "operation_id": row["operation_id"],
        "method": row["method"],
        "path": row["path"],
        "base_url": row["base_url"],
        "summary": row["summary"],
        "params_schema": _loads(row["params_schema"]),
        "request_schema": _loads(row["request_schema"]),
        "response_schema": _loads(row["response_schema"]),
        "auth": _loads(row["auth"]),
    }


def get_operation(op_id: int) -> Optional[dict]:
    """executor 의 operation_resolver 용."""
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM operations WHERE id=?", (op_id,)).fetchone()
        return _op_row_to_dict(row) if row else None
    finally:
        conn.close()


def list_operations(spec_id: int) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM operations WHERE spec_id=? ORDER BY id", (spec_id,)
        ).fetchall()
        return [_op_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def list_specs() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, name, source_type, spec_version, created_at FROM specs ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
