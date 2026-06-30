"""Formatting utilities that turn store query results into LLM-friendly text.

These are PURE functions — they do not call the store, perform no I/O, and
make no decisions.  The LLM (or a human reading the web dashboard) does the
actual analysis.
"""

from __future__ import annotations
from datetime import datetime, timezone


def format_summary(summary: dict) -> str:
    """Render a query_summary() dict as a concise text block."""
    total = summary.get("total", 0)
    ok = summary.get("ok", 0)
    warn = summary.get("warn", 0)
    crit = summary.get("crit", 0)
    if total == 0:
        return "No inspection results found."
    lines = [
        f"Total inspections: {total}",
        f"  OK:   {ok}",
        f"  WARN: {warn}",
        f"  CRIT: {crit}",
    ]
    return "\n".join(lines)


def format_trend(trend: list[dict], host: str, check: str,
                 metric: str) -> str:
    """Render a query_trend() result as a text table with per-point deltas.

    Example output::

        Trend for web-1 / disk_usage / max_pct (7 days)
        ┌─────────────────────┬────────┬──────────┐
        │ ts                  │  value │     Δ    │
        ├─────────────────────┼────────┼──────────┤
        │ 2026-06-22T08:00:00 │   45.0 │        - │
        │ 2026-06-23T08:00:00 │   50.0 │   +5.00  │
        │ 2026-06-24T08:00:00 │   62.0 │  +12.00  │
        └─────────────────────┴────────┴──────────┘
    """
    if not trend:
        return f"No trend data for {host} / {check} / {metric}."

    header = f"Trend for {host} / {check} / {metric} ({len(trend)} points)"
    rows: list[str] = []
    prev: float | None = None
    for i, pt in enumerate(trend):
        ts = pt["ts"][:19]  # truncate sub-second for readability
        val = pt["value"]
        if prev is None:
            delta = "-"
        else:
            d = float(val) - float(prev)
            delta = f"{d:+.2f}"
        rows.append(f"  {ts}  {val:>8}  {delta:>8}")
        prev = float(val)

    return header + "\n" + "\n".join(rows)


def format_correlation(records: list[dict]) -> str:
    """Group inspection records by run_id then by host, showing all checks
    that ran together in one sweep.

    Each record should have: run_id, ts, host, check_name, status, value.
    """
    if not records:
        return "No inspection records to correlate."

    # Group by run_id → host
    groups: dict[str, dict[str, list[dict]]] = {}
    for r in records:
        rid = r.get("run_id", "unknown")
        host = r.get("host", "?")
        groups.setdefault(rid, {}).setdefault(host, []).append(r)

    lines: list[str] = []
    for rid, hosts in sorted(groups.items()):
        first_ts = next(iter(next(iter(hosts.values())))).get("ts", "")[:19]
        lines.append(f"\n=== run {rid} ({first_ts}) ===")
        for host, checks in sorted(hosts.items()):
            items = ", ".join(
                f"{c['check_name']}={c['status']}" for c in checks
            )
            lines.append(f"  {host}: {items}")

    return "\n".join(lines).strip()
