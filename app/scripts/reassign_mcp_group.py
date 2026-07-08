"""
[MCP 그룹 재배정] 워크플로우의 mcp_group 변경

목적
  워크플로우를 논리 그룹으로 분리한다.
    - common         : 단지정보·부과공통 등 횡단 조회 (슈퍼바이저 레벨)
    - <메뉴키>(예 resident) : 메뉴별 하위 API (어드바이저 레벨)

안전장치
  - 실행 전 DB 백업(mcp_provider.db.bak_<ts>)
  - workflows.updated_at 갱신 → 실행 중 MCP 서버가 변경 감지
  - --dry-run 으로 변경 없이 미리보기

실행 (Windows, app 디렉터리에서):
  venv\\Scripts\\python scripts\\reassign_mcp_group.py --list
  venv\\Scripts\\python scripts\\reassign_mcp_group.py --wf 6,7 --group common --dry-run
  venv\\Scripts\\python scripts\\reassign_mcp_group.py --wf 6,7 --group common
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("MCP_DB_PATH", APP_DIR / "mcp_provider.db"))

_VALID_GROUP = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


def _connect():
    con = sqlite3.connect(str(DB_PATH)); con.row_factory = sqlite3.Row
    return con


def _print_list(cur):
    print(f"{'id':>3}  {'exposed':<7}  {'group':<14}  name")
    for w in cur.execute(
        "SELECT id, mcp_exposed, mcp_group, name FROM workflows ORDER BY id"
    ):
        print(f"{w['id']:>3}  {w['mcp_exposed']!s:<7}  {(w['mcp_group'] or '-'):<14}  {w['name']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="현재 그룹 현황만 출력")
    ap.add_argument("--wf", help="대상 워크플로우 id (콤마 구분, 예: 6,7)")
    ap.add_argument("--group", help="배정할 그룹명 (예: common, resident)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not DB_PATH.exists():
        print(f"✗ DB 없음: {DB_PATH}")
        return 1

    con = _connect(); cur = con.cursor()

    if args.list or not (args.wf and args.group):
        print("=== 현재 워크플로우 그룹 현황 ===")
        _print_list(cur)
        if args.list:
            return 0
        print("\n사용법: --wf 6,7 --group common [--dry-run]")
        return 0

    if not _VALID_GROUP.match(args.group):
        print(f"✗ 그룹명 형식 오류: {args.group} (영문/숫자/_.- 1~64자)")
        return 1

    try:
        wf_ids = [int(x) for x in args.wf.split(",") if x.strip()]
    except ValueError:
        print(f"✗ --wf 형식 오류: {args.wf}")
        return 1

    rows = cur.execute(
        f"SELECT id, mcp_group, name FROM workflows WHERE id IN ({','.join('?'*len(wf_ids))})",
        wf_ids,
    ).fetchall()
    found = {r["id"] for r in rows}
    missing = [i for i in wf_ids if i not in found]
    if missing:
        print(f"✗ 존재하지 않는 워크플로우: {missing}")
        return 1

    print("=== 변경 예정 ===")
    for r in rows:
        print(f"  id {r['id']}: '{r['mcp_group'] or '-'}' → '{args.group}'  ({r['name']})")

    if args.dry_run:
        print("\n[dry-run] 변경하지 않았습니다.")
        return 0

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = DB_PATH.with_suffix(DB_PATH.suffix + f".bak_{ts}")
    shutil.copy2(DB_PATH, backup)
    print(f"\n백업 생성: {backup.name}")

    cur.executemany(
        "UPDATE workflows SET mcp_group=?, updated_at=datetime('now') WHERE id=?",
        [(args.group, i) for i in wf_ids],
    )
    con.commit()
    print("✓ 적용 완료.\n")
    print("=== 변경 후 현황 ===")
    _print_list(cur)
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
