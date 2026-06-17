"""더미 API 서버 (:8000) — 사용자 end-to-end 테스트용.

기동:  PYTHONPATH=. uvicorn tools.dummy_api:app --port 8000
OpenAPI 스펙은 http://localhost:8000/openapi.json 에서 자동 노출됨.
"""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Dummy API",
    servers=[{"url": "http://localhost:8000"}],
)

_USERS = {
    1: {"id": 1, "name": "김철일", "email": "chungil@example.com"},
    2: {"id": 2, "name": "이영희", "email": "younghee@example.com"},
}


@app.get("/users/{user_id}", summary="사용자 단건 조회")
def get_user(user_id: int):
    return _USERS.get(user_id, {"id": user_id, "name": "unknown"})


class Order(BaseModel):
    user_id: int
    item: str
    qty: int = 1


@app.post("/orders", summary="주문 생성")
def create_order(order: Order):
    user = _USERS.get(order.user_id, {"name": "unknown"})
    return {"order_id": 1001, "user": user["name"], "item": order.item, "qty": order.qty, "status": "created"}


@app.get("/health", summary="헬스 체크")
def health():
    return {"ok": True}
