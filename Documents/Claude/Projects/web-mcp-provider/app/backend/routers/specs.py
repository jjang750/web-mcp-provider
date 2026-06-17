from __future__ import annotations
import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from backend import engine_bridge
from backend.models import FromUrlRequest, OperationOut, SpecUploadResult
from backend.repositories import specs as specs_repo

router = APIRouter(prefix="/api", tags=["specs"])


@router.post("/specs/upload", response_model=SpecUploadResult)
async def upload_spec(file: UploadFile = File(...)):
    raw_bytes = await file.read()
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(400, "스펙 파일을 UTF-8로 읽을 수 없습니다.")
    try:
        parsed = engine_bridge.parse_openapi(raw, source_hint=file.filename)
    except Exception as exc:
        raise HTTPException(400, f"스펙 파싱 실패: {exc}")
    name = (file.filename or "spec").rsplit(".", 1)[0]
    return specs_repo.create_spec_with_operations(name, "file", file.filename, raw, parsed)


@router.post("/specs/from-url", response_model=SpecUploadResult)
def spec_from_url(req: FromUrlRequest):
    if not (req.url.startswith("http://") or req.url.startswith("https://")):
        raise HTTPException(400, "URL에 http:// 또는 https:// 스킴이 필요합니다.")
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True, trust_env=False) as cli:
            resp = cli.get(req.url)
        resp.raise_for_status()
        raw = resp.text
    except httpx.HTTPError as exc:
        raise HTTPException(400, f"URL에서 스펙을 가져오지 못했습니다: {exc}")
    try:
        parsed = engine_bridge.parse_openapi(raw, source_hint=req.url)
    except Exception as exc:
        raise HTTPException(400, f"스펙 파싱 실패: {exc}")
    name = req.name or req.url.rsplit("/", 1)[-1] or "spec"
    return specs_repo.create_spec_with_operations(name, "url", req.url, raw, parsed)


@router.get("/specs")
def list_specs():
    return specs_repo.list_specs()


@router.get("/specs/{spec_id}/operations", response_model=list[OperationOut])
def list_operations(spec_id: int):
    return specs_repo.list_operations(spec_id)
