"""operations 라우터 — 단일 오퍼레이션 조회 + 응답 필드 미리보기."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.models import OperationOut
from backend.repositories import specs as specs_repo
from engine import schema_fields

router = APIRouter(prefix="/api", tags=["operations"])


@router.get("/operations/{operation_id}", response_model=OperationOut)
def get_operation(operation_id: int):
    op = specs_repo.get_operation(operation_id)
    if op is None:
        raise HTTPException(404, "오퍼레이션을 찾을 수 없습니다.")
    return op


@router.get("/operations/{operation_id}/response-fields")
def get_response_fields(operation_id: int):
    """노드 리턴값 미리보기 — 응답 스키마의 $ref 를 해소해 JSONPath 필드 목록·예시 반환."""
    op = specs_repo.get_operation(operation_id)
    if op is None:
        raise HTTPException(404, "오퍼레이션을 찾을 수 없습니다.")
    raw = specs_repo.get_spec_raw(op["spec_id"]) or ""
    return schema_fields.response_fields(op.get("response_schema"), raw)
