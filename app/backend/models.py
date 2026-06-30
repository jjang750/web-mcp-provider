"""Pydantic 와이어 모델 (사양서 §2 계약).

엣지 매핑 키는 "from"/"to" 로 고정. Python 예약어 회피를 위해 alias 사용.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

NodeType = Literal["api_call", "start", "end", "transform", "condition", "switch", "merge", "filter"]
ExecStatus = Literal["running", "success", "failed"]
NodeStatus = Literal["success", "failed", "skipped", "planned"]


class Position(BaseModel):
    x: float = 0
    y: float = 0


class NodeParams(BaseModel):
    model_config = ConfigDict(extra="allow")
    path: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    header: dict[str, Any] = Field(default_factory=dict)
    body: Any = None


class Node(BaseModel):
    id: str
    type: NodeType = "api_call"
    label: Optional[str] = None
    operation_id: Optional[int] = None
    base_url: Optional[str] = None
    # 조회/변경 구분 명시값. None 이면 실행기가 HTTP 메서드로 추론(GET/HEAD/OPTIONS=조회).
    read_only: Optional[bool] = None
    params: NodeParams = Field(default_factory=NodeParams)
    position: Position = Field(default_factory=Position)


class DataMap(BaseModel):
    # 와이어 키 "from"/"to" 고정
    model_config = ConfigDict(populate_by_name=True)
    from_: str = Field(alias="from")
    to: str


class Edge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: str
    source: str
    target: str
    data_mapping: list[DataMap] = Field(default_factory=list)
    # condition 노드의 분기 라벨("true"/"false"). 일반 엣지는 None.
    label: Optional[str] = None


class WorkflowGraph(BaseModel):
    workflow_id: int
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class NodeLog(BaseModel):
    node_key: str
    seq: int
    status: NodeStatus
    input: Any = None
    output: Any = None
    error: Optional[str] = None
    timestamp: Optional[str] = None


class ExecutionResult(BaseModel):
    execution_id: Optional[int] = None
    workflow_id: int
    status: ExecStatus
    dry_run: bool = False
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result: Any = None
    final: Any = None
    planned_actions: list[Any] = Field(default_factory=list)
    logs: list[NodeLog] = Field(default_factory=list)


# ---- API 입출력 모델 ----
class SpecUploadResult(BaseModel):
    spec_id: int
    connection_id: Optional[int] = None
    name: str
    spec_version: Optional[str] = None
    base_url: Optional[str] = None
    operation_count: int
    warnings: list[str] = Field(default_factory=list)


class OperationOut(BaseModel):
    id: int
    spec_id: int
    operation_id: Optional[str] = None
    method: str
    path: str
    base_url: Optional[str] = None
    summary: Optional[str] = None
    params_schema: Any = None
    request_schema: Any = None
    response_schema: Any = None
    auth: Any = None


class WorkflowSummary(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    mcp_exposed: bool = False
    mcp_group: Optional[str] = None
    mcp_tool_name: Optional[str] = None
    updated_at: Optional[str] = None
    node_count: int = 0
    methods: list[str] = Field(default_factory=list)
    endpoints: list[dict] = Field(default_factory=list)
    apis: list[dict] = Field(default_factory=list)


class WorkflowDetail(WorkflowSummary):
    nodes: list[Node] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)


class WorkflowCreate(BaseModel):
    name: str
    description: Optional[str] = None


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    nodes: Optional[list[Node]] = None
    edges: Optional[list[Edge]] = None


class AuthConfig(BaseModel):
    """인증 설정 — 시크릿은 영속하지 않음."""
    model_config = ConfigDict(extra="allow")
    type: Optional[Literal["bearer", "basic", "apikey"]] = None
    token: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    key: Optional[str] = None
    value: Optional[str] = None
    location: Optional[Literal["header", "query"]] = "header"
    name: Optional[str] = None  # apikey 헤더/쿼리 이름


class RunRequest(BaseModel):
    initial_input: Any = None
    auth: Optional[AuthConfig] = None
    # True 이면 변경성 호출을 실행하지 않고 실행 계획(planned_actions)만 반환(dry-run)
    dry_run: bool = False


class ExposeRequest(BaseModel):
    exposed: bool
    group: Optional[str] = None
    tool_name: Optional[str] = None


class FromUrlRequest(BaseModel):
    url: str
    name: Optional[str] = None
    connection_id: Optional[int] = None


AuthType = Literal["none", "bearer", "apikey", "basic"]


class ConnectionCreate(BaseModel):
    name: str
    base_url: Optional[str] = None
    auth_type: AuthType = "none"
    auth_config: dict = Field(default_factory=dict)


class ConnectionUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    auth_type: Optional[AuthType] = None
    auth_config: Optional[dict] = None
    enabled: Optional[bool] = None
