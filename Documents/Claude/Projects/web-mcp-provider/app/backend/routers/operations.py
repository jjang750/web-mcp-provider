"""operations 라우터 — 단일 오퍼레이션 조회."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models import OperationOut
from backend.repositories import specs as specs_repo

router = APIRouter(prefix="/api", tags=["operations"])


@router.get("/operations/{operation_id}", response_model=OperationOut)
def get_operation(operation_id: int):
    op = specs_repo.get_operation(operation_id)
    if op is None:
        raise HTTPException(404, "오퍼레이션을 찾을 수 없습니다.")
    return op
