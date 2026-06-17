"""executions 라우터 — 실행 결과 조회."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.repositories import executions as exec_repo

router = APIRouter(prefix="/api", tags=["executions"])


@router.get("/executions/{execution_id}")
def get_execution(execution_id: int):
    res = exec_repo.get(execution_id)
    if res is None:
        raise HTTPException(404, "실행 결과를 찾을 수 없습니다.")
    return res
