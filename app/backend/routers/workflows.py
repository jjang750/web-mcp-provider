"""workflows 라우터 — CRUD + 실행(run) + MCP 노출(expose)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend import engine_bridge
from backend.models import (
    ExposeRequest,
    RunRequest,
    WorkflowCreate,
    WorkflowDetail,
    WorkflowSummary,
    WorkflowUpdate,
)
from backend.repositories import executions as exec_repo
from backend.repositories import specs as specs_repo
from backend.repositories import workflows as wf_repo

router = APIRouter(prefix="/api", tags=["workflows"])


@router.get("/workflows", response_model=list[WorkflowSummary])
def list_workflows():
    return wf_repo.list_all()


@router.post("/workflows", response_model=WorkflowDetail)
def create_workflow(req: WorkflowCreate):
    wf_id = wf_repo.create(req.name, req.description)
    return wf_repo.get_detail(wf_id)


@router.get("/workflows/{workflow_id}", response_model=WorkflowDetail)
def get_workflow(workflow_id: int):
    detail = wf_repo.get_detail(workflow_id)
    if detail is None:
        raise HTTPException(404, "워크플로우를 찾을 수 없습니다.")
    return detail


@router.put("/workflows/{workflow_id}", response_model=WorkflowDetail)
def update_workflow(workflow_id: int, req: WorkflowUpdate):
    nodes = [n.model_dump(by_alias=True) for n in req.nodes] if req.nodes is not None else None
    edges = [e.model_dump(by_alias=True) for e in req.edges] if req.edges is not None else None
    detail = wf_repo.update(
        workflow_id, name=req.name, description=req.description, nodes=nodes, edges=edges
    )
    if detail is None:
        raise HTTPException(404, "워크플로우를 찾을 수 없습니다.")
    return detail


@router.delete("/workflows/{workflow_id}")
def delete_workflow(workflow_id: int):
    if not wf_repo.delete(workflow_id):
        raise HTTPException(404, "워크플로우를 찾을 수 없습니다.")
    return {"deleted": True, "id": workflow_id}


@router.post("/workflows/{workflow_id}/run")
def run_workflow(workflow_id: int, req: RunRequest):
    graph = wf_repo.get_graph(workflow_id)
    if graph is None:
        raise HTTPException(404, "워크플로우를 찾을 수 없습니다.")
    auth = req.auth.model_dump(exclude_none=True) if req.auth else None
    result = engine_bridge.run_workflow(
        graph,
        initial_input=req.initial_input,
        auth=auth,
        operation_resolver=specs_repo.get_operation,
        dry_run=req.dry_run,
    )
    exec_id = exec_repo.save(result, source="web-dryrun" if req.dry_run else "web")
    result["execution_id"] = exec_id
    return result


@router.put("/workflows/{workflow_id}/expose")
def expose_workflow(workflow_id: int, req: ExposeRequest):
    res = wf_repo.set_expose(workflow_id, req.exposed, req.group, req.tool_name)
    if res is None:
        raise HTTPException(404, "워크플로우를 찾을 수 없습니다.")
    return res
