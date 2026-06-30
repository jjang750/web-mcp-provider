"""connections (API 연결) 리포지토리.

API 연결 = base_url + 인증을 1회 관리하는 단위. 스펙(specs.connection_id)이 연결에 소속되고,
노드→오퍼레이션→스펙→연결 순으로 실행 시 base_url/인증이 자동 결정된다.

auth_config 는 TEXT(json.dumps)로 저장. 시크릿(token/value/password)은 DB 평문 저장이며,
API 응답에서는 mask_auth() 로 마스킹한다(원본은 get_auth()/get_for_resolver() 만 반환).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from backend.db import connect

MASK = "••••••••"
SECRET_KEYS = ("token", "value", "password")


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


def mask_auth(auth_config: Optional[dict]) -> dict:
    """시크릿 필드를 마스킹하고 보유 여부(has_*)를 표시."""
    cfg = dict(auth_config or {})
    out: dict = {}
    for k, v in cfg.items():
        if k in SECRET_KEYS:
            out[k] = MASK if v else ""
            out["has_" + k] = bool(v)
        else:
            out[k] = v
    return out


def _merge_secrets(existing: Optional[dict], incoming: Optional[dict]) -> dict:
    """들어온 auth_config 에서 마스킹값(MASK)은 기존 값을 유지, 그 외는 교체."""
    existing = dict(existing or {})
    incoming = dict(incoming or {})
    merged = dict(incoming)
    for k in SECRET_KEYS:
        if k in incoming and incoming[k] == MASK:
            if k in existing:
                merged[k] = existing[k]
            else:
                merged.pop(k, None)
        # has_* 보조 플래그는 저장하지 않음
    for k in list(merged.keys()):
        if k.startswith("has_"):
            merged.pop(k, None)
    return merged


def _row_to_dict(row, *, mask: bool = True) -> dict:
    cfg = _loads(row["auth_config"], {}) or {}
    return {
        "id": row["id"],
        "name": row["name"],
        "base_url": row["base_url"],
        "auth_type": row["auth_type"] or "none",
        "auth_config": mask_auth(cfg) if mask else cfg,
        "enabled": bool(row["enabled"]),
        "updated_at": row["updated_at"] if "updated_at" in row.keys() else None,
    }


def list_all(*, mask: bool = True) -> list[dict]:
    conn = connect()
    try:
        rows = conn.execute("SELECT * FROM connections ORDER BY id").fetchall()
        out = []
        for r in rows:
            d = _row_to_dict(r, mask=mask)
            d["spec_count"] = conn.execute(
                "SELECT COUNT(*) c FROM specs WHERE connection_id=?", (r["id"],)
            ).fetchone()["c"]
            d["operation_count"] = conn.execute(
                "SELECT COUNT(*) c FROM operations o JOIN specs s ON o.spec_id=s.id "
                "WHERE s.connection_id=?",
                (r["id"],),
            ).fetchone()["c"]
            d["workflow_count"] = conn.execute(
                "SELECT COUNT(DISTINCT n.workflow_id) c FROM nodes n "
                "JOIN operations o ON n.operation_id=o.id "
                "JOIN specs s ON o.spec_id=s.id WHERE s.connection_id=?",
                (r["id"],),
            ).fetchone()["c"]
            out.append(d)
        return out
    finally:
        conn.close()


def get(connection_id: int, *, mask: bool = True) -> Optional[dict]:
    conn = connect()
    try:
        r = conn.execute("SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone()
        return _row_to_dict(r, mask=mask) if r else None
    finally:
        conn.close()


def create(name: str, base_url: Optional[str], auth_type: str, auth_config: Optional[dict]) -> int:
    conn = connect()
    try:
        cur = conn.execute(
            "INSERT INTO connections (name, base_url, auth_type, auth_config, enabled, created_at, updated_at) "
            "VALUES (?,?,?,?,1,?,?)",
            (name, base_url, auth_type or "none", _dumps(_merge_secrets(None, auth_config)), _now(), _now()),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def update(
    connection_id: int,
    *,
    name: Optional[str] = None,
    base_url: Optional[str] = None,
    auth_type: Optional[str] = None,
    auth_config: Optional[dict] = None,
    enabled: Optional[bool] = None,
) -> Optional[dict]:
    conn = connect()
    try:
        row = conn.execute("SELECT * FROM connections WHERE id=?", (connection_id,)).fetchone()
        if not row:
            return None
        if name is not None:
            conn.execute("UPDATE connections SET name=? WHERE id=?", (name, connection_id))
        if base_url is not None:
            conn.execute("UPDATE connections SET base_url=? WHERE id=?", (base_url or None, connection_id))
        if auth_type is not None:
            conn.execute("UPDATE connections SET auth_type=? WHERE id=?", (auth_type or "none", connection_id))
        if auth_config is not None:
            existing = _loads(row["auth_config"], {}) or {}
            merged = _merge_secrets(existing, auth_config)
            conn.execute("UPDATE connections SET auth_config=? WHERE id=?", (_dumps(merged), connection_id))
        if enabled is not None:
            conn.execute("UPDATE connections SET enabled=? WHERE id=?", (1 if enabled else 0, connection_id))
        conn.execute("UPDATE connections SET updated_at=? WHERE id=?", (_now(), connection_id))
        conn.commit()
    finally:
        conn.close()
    return get(connection_id)


def usage(connection_id: int) -> dict:
    """이 연결(API)을 호출하는 워크플로우 목록/개수. 삭제 전 영향 범위 확인용."""
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT w.id AS id, w.name AS name FROM workflows w "
            "JOIN nodes n ON n.workflow_id=w.id "
            "JOIN operations o ON n.operation_id=o.id "
            "JOIN specs s ON o.spec_id=s.id "
            "WHERE s.connection_id=? ORDER BY w.id",
            (connection_id,),
        ).fetchall()
        wfs = [{"id": r["id"], "name": r["name"]} for r in rows]
        node_count = conn.execute(
            "SELECT COUNT(*) c FROM nodes n JOIN operations o ON n.operation_id=o.id "
            "JOIN specs s ON o.spec_id=s.id WHERE s.connection_id=?",
            (connection_id,),
        ).fetchone()["c"]
        return {"workflow_count": len(wfs), "node_count": node_count, "workflows": wfs}
    finally:
        conn.close()


def delete(connection_id: int) -> Optional[dict]:
    """연결 + 소속 스펙/오퍼레이션을 완전 삭제(되돌릴 수 없음).

    삭제되는 오퍼레이션을 참조하던 워크플로우 노드는 operation_id 를 NULL 로 해제해
    FK 위반 없이 삭제하고(노드 자체는 보존), 영향받은 워크플로우/노드 수를 반환한다.
    """
    conn = connect()
    try:
        row = conn.execute("SELECT id FROM connections WHERE id=?", (connection_id,)).fetchone()
        if not row:
            return None
        info = usage(connection_id)
        # 1) 노드 바인딩 해제(노드는 남김 — 사용자가 재지정)
        conn.execute(
            "UPDATE nodes SET operation_id=NULL WHERE operation_id IN "
            "(SELECT o.id FROM operations o JOIN specs s ON o.spec_id=s.id WHERE s.connection_id=?)",
            (connection_id,),
        )
        # 2) 오퍼레이션 삭제(스펙 CASCADE 로도 지워지나 명시 삭제로 안전)
        conn.execute(
            "DELETE FROM operations WHERE spec_id IN (SELECT id FROM specs WHERE connection_id=?)",
            (connection_id,),
        )
        # 3) 스펙 삭제
        conn.execute("DELETE FROM specs WHERE connection_id=?", (connection_id,))
        # 4) 연결 삭제
        conn.execute("DELETE FROM connections WHERE id=?", (connection_id,))
        conn.commit()
        return {
            "deleted": True,
            "id": connection_id,
            "affected_workflows": info["workflow_count"],
            "detached_nodes": info["node_count"],
        }
    finally:
        conn.close()


def get_auth(connection_id: Optional[int]) -> Optional[dict]:
    """executor 용 — 원본 시크릿 포함 인증 dict({type, ...}) 반환. none/미설정이면 None."""
    if connection_id is None:
        return None
    conn = connect()
    try:
        r = conn.execute(
            "SELECT auth_type, auth_config FROM connections WHERE id=? AND enabled=1",
            (connection_id,),
        ).fetchone()
        if not r:
            return None
        atype = r["auth_type"] or "none"
        if atype == "none":
            return None
        cfg = _loads(r["auth_config"], {}) or {}
        return {"type": atype, **cfg}
    finally:
        conn.close()


def list_operations(connection_id: int) -> list[dict]:
    """연결에 소속된 모든 스펙의 오퍼레이션(팔레트용)."""
    from backend.repositories.specs import _op_row_to_dict  # 지연 import(순환 회피)

    conn = connect()
    try:
        rows = conn.execute(
            "SELECT o.* FROM operations o JOIN specs s ON o.spec_id=s.id "
            "WHERE s.connection_id=? ORDER BY o.id",
            (connection_id,),
        ).fetchall()
        return [_op_row_to_dict(r) for r in rows]
    finally:
        conn.close()
