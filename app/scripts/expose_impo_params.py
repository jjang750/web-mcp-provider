"""
[②-서버] 워크플로우 'get_impo_bill_detail_yearmm'(id=6) 파라미터 노출 마이그레이션

목적
  노드 "1"(관리비·부과 조회, op 520)의 query 에 정적값으로 박힌
  aptcd/yearmon/dong/ho 를 제거 → build_input_schema 가 이들을 MCP 입력으로 노출.
  (aptcd/yearmon = 필수, dong/ho = 선택)

안전장치
  - 실행 전 DB 를 mcp_provider.db.bak_<timestamp> 로 백업.
  - workflows.updated_at 갱신 → 실행 중인 MCP 서버가 변경 감지(tools/list_changed).
  - --dry-run 으로 변경 없이 미리보기 가능.

실행 (Windows, repo 의 app 디렉터리에서):
  venv\\Scripts\\python scripts\\expose_impo_params.py --dry-run
  venv\\Scripts\\python scripts\\expose_impo_params.py
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# app/ 를 import 경로에 추가 (build_input_schema 미리보기용)
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))

WORKFLOW_ID = 6
NODE_KEY = "1"
CLEAR_QUERY_KEYS = ["aptcd", "yearmon", "dong", "ho"]

DB_PATH = Path(os.environ.get("MCP_DB_PATH", APP_DIR / "mcp_provider.db"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="변경 없이 미리보기")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"✗ DB 없음: {DB_PATH}")
        return 1

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    row = cur.execute(
        "SELECT id, params FROM nodes WHERE workflow_id=? AND node_key=?",
        (WORKFLOW_ID, NODE_KEY),
    ).fetchone()
    if not row:
        print(f"✗ 노드 없음: wf={WORKFLOW_ID}, node_key={NODE_KEY}")
        return 1

    params = json.loads(row["params"]) if row["params"] else {"query": {}}
    query = params.get("query") or {}
    before = {k: query.get(k) for k in CLEAR_QUERY_KEYS}
    print("현재 정적값:", json.dumps(before, ensure_ascii=False))

    for k in CLEAR_QUERY_KEYS:
        query.pop(k, None)
    params["query"] = query
    new_params = json.dumps(params, ensure_ascii=False)

    # build_input_schema 미리보기
    try:
        from backend.repositories import workflows as wf_repo  # noqa
        from backend import mcp_server  # noqa
        # 메모리상 그래프에 변경 반영해 스키마 미리보기
        graph = wf_repo.get_graph(WORKFLOW_ID)
        for n in graph.get("nodes", []):
            if n.get("id") == NODE_KEY:
                n.setdefault("params", {})["query"] = query
        schema = mcp_server.build_input_schema(graph)
        schema.setdefault("properties", {})["dry_run"] = {"type": "boolean"}
        print("\n변경 후 예상 inputSchema:")
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"(스키마 미리보기 생략: {e})")

    if args.dry_run:
        print("\n[dry-run] 변경하지 않았습니다.")
        return 0

    # 백업
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.with_suffix(DB_PATH.suffix + f".bak_{ts}")
    shutil.copy2(DB_PATH, backup)
    print(f"\n백업 생성: {backup.name}")

    cur.execute("UPDATE nodes SET params=? WHERE id=?", (new_params, row["id"]))
    cur.execute(
        "UPDATE workflows SET updated_at=datetime('now') WHERE id=?", (WORKFLOW_ID,)
    )
    con.commit()
    con.close()
    print("✓ 적용 완료. MCP 서버 재연결(또는 폴러 감지) 시 파라미터가 노출됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
