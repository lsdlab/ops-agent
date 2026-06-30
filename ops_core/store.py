from __future__ import annotations
import json
import sqlite3
from datetime import datetime, timedelta, timezone
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
    value_json TEXT NOT NULL,
    raw_stdout TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    host TEXT NOT NULL,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    value_json TEXT NOT NULL,
    raw_stdout TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON command_audit(ts);
CREATE INDEX IF NOT EXISTS idx_insp_ts ON inspection_runs(ts, host);
CREATE INDEX IF NOT EXISTS idx_alert_ts ON alert_history(ts);
"""

_MIGRATIONS = [
    # Add raw_stdout column to existing inspection_runs tables.
    "ALTER TABLE inspection_runs ADD COLUMN raw_stdout TEXT DEFAULT ''",
]


def _excerpt(text: str, limit: int = 2000) -> str:
    if text is None:
        return ""
    return text if len(text) <= limit else text[:limit] + "...[truncated]"


class Store:
    def __init__(self, path: str | Path, check_same_thread: bool = True):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path),
                                    check_same_thread=check_same_thread)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        # Apply forward-compatible migrations (ignore "duplicate column" errors).
        for stmt in _MIGRATIONS:
            try:
                self.conn.execute(stmt)
            except sqlite3.OperationalError:
                pass
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
                          status: Status, value: dict,
                          raw_stdout: str = "") -> None:
        self.conn.execute(
            "INSERT INTO inspection_runs"
            " (run_id, ts, host, check_name, status, value_json, raw_stdout)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (run_id, _now(), host, check_name, status.value, json.dumps(value),
             _excerpt(raw_stdout)),
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

    def query_inspection(self, *, host: str | None = None,
                         check_name: str | None = None,
                         status: str | None = None,
                         run_id: str | None = None,
                         ts_from: str | None = None,
                         ts_to: str | None = None,
                         limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM inspection_runs WHERE 1=1"
        args: list = []
        if host is not None:
            sql += " AND host = ?"
            args.append(host)
        if check_name is not None:
            sql += " AND check_name = ?"
            args.append(check_name)
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        if run_id is not None:
            sql += " AND run_id = ?"
            args.append(run_id)
        if ts_from is not None:
            sql += " AND ts >= ?"
            args.append(ts_from)
        if ts_to is not None:
            sql += " AND ts <= ?"
            args.append(ts_to)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in self.conn.execute(sql, args)]
        for r in rows:
            if "value_json" in r:
                r["value"] = json.loads(r.pop("value_json"))
        return rows

    def query_summary(self, *, host: str | None = None,
                      check_name: str | None = None,
                      ts_from: str | None = None,
                      ts_to: str | None = None) -> dict:
        """Return aggregate counts and distinct hosts/checks."""
        sql = "SELECT status, COUNT(*) as cnt FROM inspection_runs WHERE 1=1"
        args: list = []
        if host is not None:
            sql += " AND host = ?"
            args.append(host)
        if check_name is not None:
            sql += " AND check_name = ?"
            args.append(check_name)
        if ts_from is not None:
            sql += " AND ts >= ?"
            args.append(ts_from)
        if ts_to is not None:
            sql += " AND ts <= ?"
            args.append(ts_to)
        sql += " GROUP BY status"
        rows = list(self.conn.execute(sql, args))
        status_counts = {r["status"]: r["cnt"] for r in rows}
        total = sum(status_counts.values())
        return {
            "total": total,
            "ok": status_counts.get("ok", 0),
            "warn": status_counts.get("warn", 0),
            "crit": status_counts.get("crit", 0),
        }

    def query_trend(self, *, host: str, check_name: str, metric_key: str,
                    lookback_days: int = 7) -> list[dict]:
        """Return time-series of a single metric for trend analysis."""
        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()
        sql = ("SELECT ts, value_json FROM inspection_runs"
               " WHERE host = ? AND check_name = ? AND ts >= ?"
               " ORDER BY ts ASC")
        points: list[dict] = []
        for r in self.conn.execute(sql, (host, check_name, since)):
            value = json.loads(r["value_json"])
            if metric_key in value:
                points.append({"ts": r["ts"], "value": value[metric_key]})
        return points

    def insert_alert(self, *, host: str, check_name: str, status: str,
                     value: dict, raw_stdout: str = "") -> None:
        self.conn.execute(
            "INSERT INTO alert_history"
            " (ts, host, check_name, status, value_json, raw_stdout)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (_now(), host, check_name, status, json.dumps(value),
             _excerpt(raw_stdout)),
        )
        self.conn.commit()

    def query_alerts(self, *, host: str | None = None, status: str | None = None,
                     limit: int = 100) -> list[dict]:
        sql = "SELECT * FROM alert_history WHERE 1=1"
        args: list = []
        if host is not None:
            sql += " AND host = ?"
            args.append(host)
        if status is not None:
            sql += " AND status = ?"
            args.append(status)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        rows = [dict(r) for r in self.conn.execute(sql, args)]
        for r in rows:
            if "value_json" in r:
                r["value"] = json.loads(r.pop("value_json"))
        return rows

    def close(self) -> None:
        self.conn.close()
