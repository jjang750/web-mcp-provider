"""SQLite 연결 + 멱등 스키마 + 컬럼 마이그레이션.

사양서 §2 데이터 모델을 그대로 구현한다. JSON 컬럼은 TEXT(json.dumps)로 저장하고
리포지토리 계층에서 (de)serialize 한다. PK는 정수, 그래프 내부 참조는 문자열 키.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# repo 루트(app/) 기준 단일 파일
DB_PATH = Path(os.environ.get("MCP_DB_PATH", Path(__file__).resolve().parent.parent / "mcp_provider.db"))

# 멱등 DDL — 존재하지 않을 때만 생성
SCHEMA = """
CREATE TABLE IF NOT EXISTS specs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    source_type   TEXT NOT NULL CHECK (source_type IN ('file','url')),
    source_ref    TEXT,
    spec_version  TEXT,
    raw_content   TEXT,
    parsed_at     TEXT,
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS operations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id         INTEGER NOT NULL REFERENCES specs(id) ON DELETE CASCADE,
    operation_id    TEXT,
    method          TEXT NOT NULL,
    path            TEXT NOT NULL,
    base_url        TEXT,
    summary         TEXT,
    params_schema   TEXT,
    request_schema  TEXT,
    response_schema TEXT,
    auth            TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workflows (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    description   TEXT,
    mcp_exposed   INTEGER NOT NULL DEFAULT 0,
    mcp_group     TEXT,
    mcp_tool_name TEXT,
    created_at    TEXT DEFAULT (datetime('now')),
    updated_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id  INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    node_key     TEXT NOT NULL,
    operation_id INTEGER REFERENCES operations(id),
    type         TEXT NOT NULL DEFAULT 'api_call',
    label        TEXT,
    base_url     TEXT,
    params       TEXT,
    position_x   REAL DEFAULT 0,
    position_y   REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS edges (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id      INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    edge_key         TEXT NOT NULL,
    source_node_key  TEXT NOT NULL,
    target_node_key  TEXT NOT NULL,
    data_mapping     TEXT
);

CREATE TABLE IF NOT EXISTS executions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id  INTEGER NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    status       TEXT,
    started_at   TEXT,
    finished_at  TEXT,
    result       TEXT
);

CREATE TABLE IF NOT EXISTS execution_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id  INTEGER NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    node_key      TEXT,
    seq           INTEGER,
    status        TEXT,
    input         TEXT,
    output        TEXT,
    error         TEXT,
    timestamp     TEXT
);
"""

# 신규 컬럼은 여기에 등록 — 기존 DB에도 ALTER 로 추가됨
# (table, column, ddl-type)
COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("workflows", "mcp_group", "TEXT"),
    ("workflows", "mcp_tool_name", "TEXT"),
    ("nodes", "base_url", "TEXT"),
]


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _apply_column_migrations(conn: sqlite3.Connection) -> None:
    """PRAGMA table_info 로 컬럼 존재 확인 후 없으면 ALTER TABLE ADD COLUMN."""
    for table, column, ddl_type in COLUMN_MIGRATIONS:
        cols = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
        if not cols:
            # 테이블 자체가 없으면 스키마 생성 단계에서 처리됨
            continue
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")


def init_db() -> None:
    """앱 lifespan 시작 시 호출. 멱등."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _apply_column_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def list_tables() -> list[str]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]
    finally:
        conn.close()
