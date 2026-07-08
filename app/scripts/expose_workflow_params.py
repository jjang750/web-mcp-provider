"""
[②-서버] 워크플로우 파라미터 노출 (범용)

지정한 워크플로우의 api_call 노드에서, 해당 오퍼레이션이 선언한 파라미터
(params_schema 의 path/query/header)에 '정적값'으로 박혀 있는 값을 제거한다.
→ build_input_schema 가 이 파라미터들을 MCP 도구 입력으로 노출하게 된다.

안전장치
  - 실행 전 DB 백업(mcp_provider.db.bak_<ts>)
  - workflows.updated_at 갱신 → 실행 중 MCP 서버가 변경 감지(tools/list_changed)
  - --dry-run 으로 변경 없이 미리보기

실행 (Windows, app 디렉터리에서):
  venv\\Scripts\\python scripts\\expose_workflow_params.py --wf 7 --dry-run
  venv\\Scripts\\python scripts\\expose_workflow_params.py --wf 7
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

APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
DB_PATH = Path(os.environ.get("MCP_DB_PATH", APP_DIR / "mcp_provider.db"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wf", type=int, required=True, help="워크플로우 id")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"✗ DB 없음: {DB_PATH}")
        return 1

    con = sqlite3.connect(str(DB_PATH)); con.row_factory = sqlite3.Row
    cur = con.cursor()

    from backend.repositories import specs as specs_repo  # noqa

    nodes = cur.execute(
        "SELECT id, node_key, operation_id, params FROM nodes "
        "WHERE workflow_id=? AND type='api_call' AND operation_id IS NOT NULL",
        (args.wf,),
    ).fetchall()
    if not nodes:
        print(f"✗ api_call 노드 없음: wf={args.wf}")
        return 1

    updates = []  # (node_id, new_params_json, cleared_list)
    for n in nodes:
        params = json.loads(n["params"]) if n["params"] else {}
        op = specs_repo.get_operation(n["operation_id"])
        if not op:
            continue
        cleared = []
        for ps in (op.get("params_schema") or []):
            loc, pname = ps.get("in"), ps.get("name")
            if loc not in ("path", "query", "header"):
                continue
            cur_val = (params.get(loc) or {}).get(pname)
            if cur_val not in (None, ""):
                params[loc].pop(pname, None)
                cleared.append(f"{loc}.{pname}={cur_val!r}")
        if cleared:
            updates.append((n["id"], json.dumps(params, ensure_ascii=False), cleared))
            print(f"노드 '{n['node_key']}' 정적값 제거: {', '.join(cleared)}")

    if not updates:
        print("변경할 정적 파라미터가 없습니다(이미 노출 상태이거나 해당 없음).")
        return 0

    # 변경 후 inputSchema 미리보기
    try:
        from backend.repositories import workflows as wf_repo  # noqa
        from backend import mcp_server  # noqa
        graph = wf_repo.get_graph(args.wf)
        id2new = {nid: json.loads(p) for nid, p, _ in updates}
        nk_by_id = {n["id"]: n["node_key"] for n in nodes}
        for g in graph.get("nodes", []):
            for nid, nk in nk_by_id.items():
                if g.get("id") == nk and nid in id2new:
                    g["params"] = id2new[nid]
        schema = mcp_server.build_input_schema(graph)
        schema.setdefault("properties", {})["dry_run"] = {"type": "boolean"}
        print("\n변경 후 예상 inputSchema:")
        print(json.dumps(schema, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"(스키마 미리보기 생략: {e})")

    if args.dry_run:
        print("\n[dry-run] 변경하지 않았습니다.")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.with_suffix(DB_PATH.suffix + f".bak_{ts}")
    shutil.copy2(DB_PATH, backup)
    print(f"\n백업 생성: {backup.name}")

    for nid, new_params, _ in updates:
        cur.execute("UPDATE nodes SET params=? WHERE id=?", (new_params, nid))
    cur.execute("UPDATE workflows SET updated_at=datetime('now') WHERE id=?", (args.wf,))
    con.commit(); con.close()
    print("✓ 적용 완료. MCP 서버 재연결 시 파라미터가 노출됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
