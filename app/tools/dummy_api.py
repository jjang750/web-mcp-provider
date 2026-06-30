"""더미 API 서버 (:8000) — 사용자 end-to-end / MCP 워크플로우 테스트용.

기동:  PYTHONPATH=. uvicorn tools.dummy_api:app --port 8000
OpenAPI 스펙은 http://localhost:8000/openapi.json 에서 자동 노출됨.
Swagger UI:  http://localhost:8000/docs

제공 메서드(MCP 워크플로우 테스트용 전체 CRUD):
  GET    /users               사용자 목록
  GET    /users/{user_id}     단건 조회
  POST   /users               생성
  PUT    /users/{user_id}     전체 교체(없으면 생성=upsert)
  PATCH  /users/{user_id}     부분 수정
  DELETE /users/{user_id}     삭제
  GET    /orders/{order_id}   주문 조회
  POST   /orders              주문 생성
  PUT    /orders/{order_id}   주문 전체 교체
  PATCH  /orders/{order_id}   주문 부분 수정
  DELETE /orders/{order_id}   주문 삭제
  GET    /health             헬스 체크
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(
    title="Dummy API",
    description="MCP 워크플로우 테스트용 더미 API (GET/POST/PUT/PATCH/DELETE).",
    version="2.0.0",
    servers=[{"url": "http://localhost:8000"}],
)

# ---------------------------------------------------------------------------
# 인메모리 저장소 (서버 재기동 시 초기화)
# ---------------------------------------------------------------------------
_USERS: dict[int, dict] = {
    1: {"id": 1, "name": "김철일", "email": "chungil@example.com"},
    2: {"id": 2, "name": "이영희", "email": "younghee@example.com"},
}
_ORDERS: dict[int, dict] = {}
_next_user_id = 3
_next_order_id = 1001


# ===========================================================================
# Users
# ===========================================================================
class UserCreate(BaseModel):
    name: str
    email: Optional[str] = None


class UserReplace(BaseModel):
    """PUT — 전체 교체(필수 필드 전부)."""
    name: str
    email: Optional[str] = None


class UserPatch(BaseModel):
    """PATCH — 부분 수정(보낸 필드만 갱신)."""
    name: Optional[str] = None
    email: Optional[str] = None


@app.get("/users", summary="사용자 목록 조회")
def list_users():
    return {"items": list(_USERS.values()), "total": len(_USERS)}


@app.get("/users/{user_id}", summary="사용자 단건 조회")
def get_user(user_id: int):
    return _USERS.get(user_id, {"id": user_id, "name": "unknown"})


@app.post("/users", status_code=201, summary="사용자 생성")
def create_user(body: UserCreate):
    global _next_user_id
    new_id = _next_user_id
    _next_user_id += 1
    user = {"id": new_id, "name": body.name, "email": body.email}
    _USERS[new_id] = user
    return {"status": "created", "user": user}


@app.put("/users/{user_id}", summary="사용자 전체 교체(upsert)")
def replace_user(user_id: int, body: UserReplace):
    existed = user_id in _USERS
    user = {"id": user_id, "name": body.name, "email": body.email}
    _USERS[user_id] = user
    return {"status": "replaced" if existed else "created", "user": user}


@app.patch("/users/{user_id}", summary="사용자 부분 수정")
def patch_user(user_id: int, body: UserPatch):
    user = _USERS.get(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    changes = body.model_dump(exclude_unset=True)
    user.update(changes)
    _USERS[user_id] = user
    return {"status": "patched", "changed": list(changes.keys()), "user": user}


@app.delete("/users/{user_id}", summary="사용자 삭제")
def delete_user(user_id: int):
    removed = _USERS.pop(user_id, None)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"user {user_id} not found")
    return {"status": "deleted", "id": user_id}


# ===========================================================================
# Orders
# ===========================================================================
class Order(BaseModel):
    user_id: int
    item: str
    qty: int = 1


class OrderPatch(BaseModel):
    user_id: Optional[int] = None
    item: Optional[str] = None
    qty: Optional[int] = None
    status: Optional[str] = None


def _order_view(order: dict) -> dict:
    user = _USERS.get(order["user_id"], {"name": "unknown"})
    return {**order, "user": user["name"]}


@app.get("/orders/{order_id}", summary="주문 단건 조회")
def get_order(order_id: int):
    order = _ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id} not found")
    return _order_view(order)


@app.post("/orders", status_code=201, summary="주문 생성")
def create_order(order: Order):
    global _next_order_id
    oid = _next_order_id
    _next_order_id += 1
    rec = {"order_id": oid, "user_id": order.user_id, "item": order.item,
           "qty": order.qty, "status": "created"}
    _ORDERS[oid] = rec
    return _order_view(rec)


@app.put("/orders/{order_id}", summary="주문 전체 교체")
def replace_order(order_id: int, order: Order):
    existed = order_id in _ORDERS
    rec = {"order_id": order_id, "user_id": order.user_id, "item": order.item,
           "qty": order.qty, "status": "updated" if existed else "created"}
    _ORDERS[order_id] = rec
    return {"status": rec["status"], **_order_view(rec)}


@app.patch("/orders/{order_id}", summary="주문 부분 수정")
def patch_order(order_id: int, body: OrderPatch):
    order = _ORDERS.get(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"order {order_id} not found")
    changes = body.model_dump(exclude_unset=True)
    order.update(changes)
    _ORDERS[order_id] = order
    return {"status": "patched", "changed": list(changes.keys()), **_order_view(order)}


@app.delete("/orders/{order_id}", summary="주문 삭제")
def delete_order(order_id: int):
    removed = _ORDERS.pop(order_id, None)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"order {order_id} not found")
    return {"status": "deleted", "order_id": order_id}


# ===========================================================================
# Misc
# ===========================================================================
@app.get("/health", summary="헬스 체크")
def health():
    return {"ok": True}
