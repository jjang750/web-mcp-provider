"""실행 로그 페이징·검색 테스트.

repo 레벨(list_recent/count_recent)과 API 레벨(/api/executions 페이징 응답)을 검증한다.
"""
import importlib

import pytest


def _result(wf_id, status="success"):
    return {
        "workflow_id": wf_id, "status": status,
        "started_at": "2026-06-18T00:00:00+00:00",
        "finished_at": "2026-06-18T00:00:01+00:00",
        "result": {}, "logs": [],
    }


def _reload_all():
    import backend.db as db
    importlib.reload(db)
    import backend.repositories.workflows as w
    importlib.reload(w)
    import backend.repositories.executions as e
    importlib.reload(e)
    db.init_db()
    return db, w, e


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "t.db"))
    _, w, e = _reload_all()
    wf_id = w.create("결제 워크플로우")
    return e, wf_id


# ---------- repo: 페이징 ----------
def test_pagination(env):
    e, wf = env
    for _ in range(7):
        e.save(_result(wf), source="web")
    assert e.count_recent() == 7
    p1 = e.list_recent(limit=3, offset=0)
    p2 = e.list_recent(limit=3, offset=3)
    p3 = e.list_recent(limit=3, offset=6)
    assert (len(p1), len(p2), len(p3)) == (3, 3, 1)
    ids = [r["execution_id"] for r in p1 + p2 + p3]
    assert ids == sorted(ids, reverse=True)  # id 내림차순
    assert len(set(ids)) == 7                # 페이지 간 중복 없음


# ---------- repo: 출처 필터 ----------
def test_source_filter(env):
    e, wf = env
    e.save(_result(wf), source="web")
    e.save(_result(wf), source="mcp", tool_name="get_impo_detail")
    e.save(_result(wf), source="mcp", tool_name="list_users")
    assert e.count_recent() == 3
    assert e.count_recent(source="web") == 1
    assert e.count_recent(source="mcp") == 2


# ---------- repo: 검색(도구명/상태/워크플로우명/조합) ----------
def test_search(env):
    e, wf = env
    e.save(_result(wf), source="mcp", tool_name="get_impo_detail")
    e.save(_result(wf), source="mcp", tool_name="list_users")
    e.save(_result(wf, status="failed"), source="web")
    assert e.count_recent(q="impo") == 1                  # 도구명
    assert e.list_recent(q="impo")[0]["tool_name"] == "get_impo_detail"
    assert e.count_recent(q="failed") == 1                # 상태
    assert e.count_recent(q="결제") == 3                  # 워크플로우명
    assert e.count_recent(source="mcp", q="users") == 1   # 출처+검색 조합
    assert e.count_recent(q="없는검색어") == 0


def test_search_by_id(env):
    e, wf = env
    eid = e.save(_result(wf), source="web")
    rows = e.list_recent(q=str(eid))
    assert any(r["execution_id"] == eid for r in rows)


# ---------- API: 페이징 응답 형식 ----------
def test_api_pagination_shape(tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_DB_PATH", str(tmp_path / "t.db"))
    _, w, e = _reload_all()
    import backend.app as app_mod
    importlib.reload(app_mod)
    wf_id = w.create("WF")
    for _ in range(3):
        e.save(_result(wf_id), source="web")
    from starlette.testclient import TestClient
    with TestClient(app_mod.app) as c:
        r = c.get("/api/executions?limit=2&offset=0").json()
        assert {"items", "total", "limit", "offset"} <= set(r.keys())
        assert r["total"] == 3 and len(r["items"]) == 2 and r["limit"] == 2
        r2 = c.get("/api/executions?limit=2&offset=2").json()
        assert len(r2["items"]) == 1
        r3 = c.get("/api/executions?limit=9999").json()
        assert r3["limit"] == 200  # 상한 클램프
