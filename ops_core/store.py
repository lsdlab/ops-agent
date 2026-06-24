from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from ops_core.models import Status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS command_audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    host TEXT NOT NULL,
    command TEXT NOT NULL,
    rc INTEGER,
    initiated_by TEXT NOT NULL,
    approved_by TEXT,
    verdict TEXT NOT NULL,
    stdout_excerpt TEXT,
    stderr_excerpt TEXT
);
CREATE TABLE IF NOT EXISTS inspection_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    host TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    value_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON command_audit(ts);
CREATE INDEX IF NOT EXISTS idx_insp_ts ON inspection_runs(ts, host);
"""


def _excerpt(text: str, limit: int = 2000) -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


class Store:
    def __init__(self, path: str | Path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def insert_audit(self, *, host: str, command: str, rc: int | None,
                     initiated_by: str, approved_by: str | None, verdict: str,
                     stdout_excerpt: str, stderr_excerpt: str) -> None:
        self.conn.execute(
            "INSERT INTO command_audit"
            " (ts, host, command, rc, initiated_by, approved_by, verdict,"
            "  stdout_excerpt, stderr_excerpt)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (_now(), host, command, rc, initiated_by, approved_by, verdict,
             _excerpt(stdout_excerpt), _excerpt(stderr_excerpt)),
        )
        self.conn.commit()

    def insert_inspection(self, *, run_id: str, host: str, check_name: str,
                          status: Status, value: dict) -> None:
        self.conn.execute(
            "INSERT INTO inspection_runs"
            " (run_id, ts, host, check_name, status, value_json)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, _now(), host, check_name, status.value, json.dumps(value)),
        )
        self.conn.commit()

    def query_audit(self, *, host: str | None = None, limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM command_audit"
        args: list = []
        if host is not None:
            sql += " WHERE host = ?"
            args.append(host)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        return [dict(r) for r in self.conn.execute(sql, args)]

    def query_inspection(self, *, host: str, check_name: str | None = None,
                         limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM inspection_runs WHERE host = ?"
        args: list = [host]
        if check_name is not None:
            sql += " AND check_name = ?"
            args.append(check_name)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in self.conn.execute(sql, args)]
        for r in rows:
            r["value"] = json.loads(r.pop("value_json"))
        return rows

    def close(self) -> None:
        self.conn.close()
