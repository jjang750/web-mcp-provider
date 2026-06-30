"""connections (API 연결) 라우터 — base_url/인증을 1회 관리하고 연결 테스트/오퍼레이션 조회."""
from __future__ import annotations

import time

import httpx
from fastapi import APIRouter, HTTPException

from backend.models import ConnectionCreate, ConnectionUpdate
from backend.repositories import connections as cx_repo
from engine.http_client import _apply_auth

router = APIRouter(prefix="/api", tags=["connections"])


@router.get("/connections")
def list_connections():
    return cx_repo.list_all(mask=True)


@router.post("/connections")
def create_connection(req: ConnectionCreate):
    cid = cx_repo.create(req.name, req.base_url, req.auth_type, req.auth_config)
    return cx_repo.get(cid)


@router.get("/connections/{connection_id}")
def get_connection(connection_id: int):
    c = cx_repo.get(connection_id)
    if c is None:
        raise HTTPException(404, "연결을 찾을 수 없습니다.")
    return c


@router.put("/connections/{connection_id}")
def update_connection(connection_id: int, req: ConnectionUpdate):
    c = cx_repo.update(
        connection_id,
        name=req.name,
        base_url=req.base_url,
        auth_type=req.auth_type,
        auth_config=req.auth_config,
        enabled=req.enabled,
    )
    if c is None:
        raise HTTPException(404, "연결을 찾을 수 없습니다.")
    return c


@router.get("/connections/{connection_id}/usage")
def connection_usage(connection_id: int):
    if cx_repo.get(connection_id) is None:
        raise HTTPException(404, "연결을 찾을 수 없습니다.")
    return cx_repo.usage(connection_id)


@router.delete("/connections/{connection_id}")
def delete_connection(connection_id: int):
    res = cx_repo.delete(connection_id)
    if res is None:
        raise HTTPException(404, "연결을 찾을 수 없습니다.")
    return res


@router.get("/connections/{connection_id}/operations")
def connection_operations(connection_id: int):
    if cx_repo.get(connection_id) is None:
        raise HTTPException(404, "연결을 찾을 수 없습니다.")
    return cx_repo.list_operations(connection_id)


@router.post("/connections/{connection_id}/test")
def test_connection(connection_id: int):
    """저장된 base_url + 인증으로 GET 요청을 보내 연결 가능 여부를 확인."""
    c = cx_repo.get(connection_id)
    if c is None:
        raise HTTPException(404, "연결을 찾을 수 없습니다.")
    base_url = (c.get("base_url") or "").strip()
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        return {"ok": False, "error": "base_url 에 http:// 또는 https:// 스킴이 필요합니다."}
    auth = cx_repo.get_auth(connection_id)  # 원본 시크릿
    headers: dict = {}
    params: dict = {}
    try:
        _apply_auth(auth, headers, params)
    except Exception:
        pass
    t0 = time.time()
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, trust_env=False) as cli:
            resp = cli.get(base_url, headers=headers or None, params=params or None)
        elapsed = int((time.time() - t0) * 1000)
        return {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "elapsed_ms": elapsed,
            "url": str(resp.request.url),
        }
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"요청 실패: {exc}", "elapsed_ms": int((time.time() - t0) * 1000)}
