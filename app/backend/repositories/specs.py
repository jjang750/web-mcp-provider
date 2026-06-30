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
    connection_id: Optional[int] = None,
) -> dict:
    """스펙 + 파싱된 오퍼레이션을 저장하고 요약을 반환.

    connection_id 가 없으면 스펙명/파싱 base_url 로 연결(API)을 자동 생성해 소속시킨다.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = connect()
    try:
        if connection_id is None:
            cur_c = conn.execute(
                "INSERT INTO connections (name, base_url, auth_type, auth_config, enabled, created_at, updated_at) "
                "VALUES (?,?, 'none', NULL, 1, ?, ?)",
                (name, parse_result.base_url, now, now),
            )
            connection_id = cur_c.lastrowid
        cur = conn.execute(
            "INSERT INTO specs (name, connection_id, source_type, source_ref, spec_version, raw_content, parsed_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, connection_id, source_type, source_ref, parse_result.spec_version, raw_content, now),
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
            "connection_id": connection_id,
            "name": name,
            "spec_version": parse_result.spec_version,
            "base_url": parse_result.base_url,
            "operation_count": len(parse_result.operations),
            "warnings": list(parse_result.warnings),
        }
    finally:
        conn.close()


def resync_operations(spec_id: int, raw_content: str, parse_result) -> dict:
    """스펙 원문을 갱신하고 오퍼레이션을 (method, path) 기준 업서트로 재동기. 연결 소속은 유지.

    기존(삭제 후 재삽입) 방식은 ① operations 를 참조하는 노드(FK)로 DELETE 가 막히고
    ② 재삽입 시 PK(id)가 바뀌어 워크플로우 노드의 operation_id 연결이 끊기는 문제가 있었다.
    → 동일 (method, path) 는 **기존 id 를 유지하며 UPDATE**(노드 연결 보존), 신규는 INSERT,
      사라진 오퍼레이션만 **참조 노드를 detach(operation_id=NULL) 후 DELETE** 한다.
    """
    now = datetime.now(timezone.utc).isoformat()
    conn = connect()
    try:
        row = conn.execute("SELECT id FROM specs WHERE id=?", (spec_id,)).fetchone()
        if not row:
            return {}
        conn.execute(
            "UPDATE specs SET raw_content=?, spec_version=?, parsed_at=? WHERE id=?",
            (raw_content, parse_result.spec_version, now, spec_id),
        )
        # 기존 오퍼레이션 (method, path) → id 매핑
        existing = {
            (r["method"], r["path"]): r["id"]
            for r in conn.execute(
                "SELECT id, method, path FROM operations WHERE spec_id=?", (spec_id,)
            ).fetchall()
        }
        seen: set = set()
        added = 0
        for op in parse_result.operations:
            key = (op.method, op.path)
            vals_common = (
                op.operation_id, op.base_url, op.summary,
                _dumps(op.params_schema), _dumps(op.request_schema),
                _dumps(op.response_schema), _dumps(op.auth),
            )
            if key in existing:  # 기존 id 유지하며 갱신 → 노드 연결 보존
                conn.execute(
                    "UPDATE operations SET operation_id=?, base_url=?, summary=?, "
                    "params_schema=?, request_schema=?, response_schema=?, auth=? WHERE id=?",
                    (*vals_common, existing[key]),
                )
                seen.add(key)
            else:  # 신규 엔드포인트
                conn.execute(
                    "INSERT INTO operations "
                    "(spec_id, operation_id, method, path, base_url, summary, params_schema, request_schema, response_schema, auth) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (spec_id, op.operation_id, op.method, op.path, *vals_common[1:]),
                )
                added += 1
        # 이번 스펙에서 사라진 오퍼레이션: 참조 노드 detach 후 삭제
        removed = 0
        detached = 0
        for key, oid in existing.items():
            if key in seen:
                continue
            cur = conn.execute("UPDATE nodes SET operation_id=NULL WHERE operation_id=?", (oid,))
            detached += cur.rowcount or 0
            conn.execute("DELETE FROM operations WHERE id=?", (oid,))
            removed += 1
        conn.commit()
        return {
            "spec_id": spec_id,
            "operation_count": len(parse_result.operations),
            "added": added,
            "updated": len(seen),
            "removed": removed,
            "detached_nodes": detached,
        }
    finally:
        conn.close()


def get_spec(spec_id: int) -> Optional[dict]:
    conn = connect()
    try:
        r = conn.execute(
            "SELECT id, name, connection_id, source_type, source_ref, spec_version FROM specs WHERE id=?",
            (spec_id,),
        ).fetchone()
        return dict(r) if r else None
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
    """executor 의 operation_resolver 용.

    오퍼레이션 + 소속 스펙의 연결(connection) base_url/인증을 함께 해소해 반환한다.
    - conn_base_url: 연결의 base_url(없으면 None)
    - auth: 연결에 설정된 인증(원본 시크릿 포함; type='none'/미설정이면 None)
    """
    conn = connect()
    try:
        row = conn.execute(
            "SELECT o.*, s.connection_id AS _connection_id "
            "FROM operations o LEFT JOIN specs s ON o.spec_id = s.id WHERE o.id=?",
            (op_id,),
        ).fetchone()
        if not row:
            return None
        d = _op_row_to_dict(row)
        cid = row["_connection_id"]
        d["connection_id"] = cid
        d["conn_base_url"] = None
        d["auth"] = None
        if cid is not None:
            c = conn.execute(
                "SELECT base_url, auth_type, auth_config, enabled FROM connections WHERE id=?",
                (cid,),
            ).fetchone()
            if c:
                d["conn_base_url"] = c["base_url"]
                atype = c["auth_type"] or "none"
                if c["enabled"] and atype != "none":
                    cfg = _loads(c["auth_config"]) or {}
                    d["auth"] = {"type": atype, **cfg}
        return d
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


def get_spec_raw(spec_id: int) -> Optional[str]:
    """스펙 원문(raw_content) — $ref 해소용."""
    conn = connect()
    try:
        row = conn.execute("SELECT raw_content FROM specs WHERE id=?", (spec_id,)).fetchone()
        return row["raw_content"] if row else None
    finally:
        conn.close()


def list_specs() -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT id, name, connection_id, source_type, source_ref, spec_version, created_at "
            "FROM specs ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
