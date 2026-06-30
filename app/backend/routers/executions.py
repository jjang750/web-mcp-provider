"""executions 라우터 — 실행 결과 조회."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.repositories import executions as exec_repo

router = APIRouter(prefix="/api", tags=["executions"])


@router.get("/executions")
def list_executions(limit: int = 50, offset: int = 0,
                    source: str | None = None, q: str | None = None):
    """감사 로그 — 실행 목록(페이징·검색). source: web|mcp, q: 워크플로우명/도구명/상태/ID 검색.

    반환: {items, total, limit, offset}.
    """
    limit = max(1, min(limit, 200))
    offset = max(0, offset)
    q = (q or "").strip() or None
    items = exec_repo.list_recent(limit=limit, offset=offset, source=source, q=q)
    total = exec_repo.count_recent(source=source, q=q)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/executions/{execution_id}")
def get_execution(execution_id: int):
    res = exec_repo.get(execution_id)
    if res is None:
        raise HTTPException(404, "실행 결과를 찾을 수 없습니다.")
    return res
