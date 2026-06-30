"""ops-daemon: scheduled read-only inspections + alerts (no LLM)."""

from __future__ import annotations
import asyncio
import sys
import time
import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.alerting import AlertSink
from ops_core.config import load_config
from ops_core.inspection import BUILTIN_CHECKS, run_check
from ops_core.inventory import load_hosts
from ops_core.models import Check, Host, Status
from ops_core.remote_exec import AsyncsshExecutor, Executor
from ops_core.store import Store

# ---- Alert state tracking (dedup) ----
# Key: "host:check" → last status string.  Alert only on transition.
_alert_state: dict[str, str] = {}
# For suppressing "noise" on first-ever run.
_first_run = True


def _should_alert(host: str, check: str, new_status: str) -> bool:
    """Return True only when the status for (host, check) has changed.

    On the very first daemon run, existing WARN/CRIT are reported once
    (as 'initial state'), so you know the starting condition, but no
    repeated alerts fire afterwards unless the status actually flips.
    """
    global _first_run
    key = f"{host}:{check}"
    old = _alert_state.get(key)
    _alert_state[key] = new_status
    if old is None:
        if _first_run:
            return True   # report initial state
        return True       # first time seeing this host:check
    return old != new_status


def _emoji(status: str) -> str:
    return {"ok": "✓", "warn": "△", "crit": "✕"}.get(status, "?")


def _colour(status: str) -> str:
    if status == "crit":
        return "\033[31m"  # red
    if status == "warn":
        return "\033[33m"  # yellow
    if status == "ok":
        return "\033[32m"  # green
    return ""


_RST = "\033[0m"


def validate_checks(checks: list[Check],
                    allowlist: Allowlist | None = None,
                    denylist: DangerDenylist | None = None) -> list[str]:
    """Return a list of problems. Empty means OK. Non-empty => refuse to start."""
    allowlist = allowlist or Allowlist(DEFAULT_READONLY)
    denylist = denylist or DangerDenylist(DEFAULT_DANGER)
    problems: list[str] = []
    for chk in checks:
        if denylist.matches(chk.command):
            problems.append(f"{chk.name}: command '{chk.command}' matches danger denylist")
        elif not allowlist.matches(chk.command):
            problems.append(f"{chk.name}: command '{chk.command}' not on read-only allowlist")
    return problems


async def run_once(hosts: list[Host], checks: list[Check], executor: Executor,
                   store: Store, sink: AlertSink, run_id: str | None = None) -> None:
    global _first_run
    run_id = run_id or str(uuid.uuid4())
    for h in hosts:
        for chk in checks:
            cr = await run_check(h, chk, executor)
            status_str = cr.status.value
            store.insert_inspection(run_id=run_id, host=cr.host,
                                    check_name=cr.check_name, status=cr.status,
                                    value=cr.value, raw_stdout=cr.raw)

            if cr.status in (Status.WARN, Status.CRIT):
                store.insert_alert(host=cr.host, check_name=cr.check_name,
                                   status=status_str, value=cr.value,
                                   raw_stdout=cr.raw)

            # ---- Alert dedup ----
            if _should_alert(cr.host, cr.check_name, status_str):
                c = _colour(status_str)
                ts = time.strftime("%H:%M:%S")
                if _first_run and cr.status in (Status.WARN, Status.CRIT):
                    tag = " (initial)"
                else:
                    tag = ""
                print(f"{c}[{status_str.upper()}]{_RST} {cr.host} {cr.check_name}"
                      f"  {_fmt_value(cr.value)}{tag}  {ts}", flush=True)

            await sink.send(cr)

    _first_run = False


def _fmt_value(value: dict) -> str:
    """Compact value display."""
    if not value:
        return ""
    parts = []
    for k, v in value.items():
        if isinstance(v, float):
            parts.append(f"{k}={v:.1f}")
        else:
            parts.append(f"{k}={v}")
    return "  ".join(parts)


def _resolve_targets(all_hosts: list[Host], spec: dict) -> list[Host]:
    tag = spec.get("hosts")
    if isinstance(tag, str) and tag.startswith("tag:"):
        return [h for h in all_hosts if tag[4:] in h.tags]
    if isinstance(tag, list):
        return [h for h in all_hosts if h.alias in tag]
    return list(all_hosts)


def build_scheduler(cfg, hosts, executor, store, sink) -> AsyncIOScheduler:
    checks = [BUILTIN_CHECKS[s["check"]] for s in cfg.schedule
              if s["check"] in BUILTIN_CHECKS]
    problems = validate_checks(checks)
    if problems:
        for p in problems:
            print(p, file=sys.stderr)
        raise SystemExit("refusing to start: inspection allowlist validation failed")

    scheduler = AsyncIOScheduler()
    for spec in cfg.schedule:
        name = spec["check"]
        if name not in BUILTIN_CHECKS:
            continue
        check = BUILTIN_CHECKS[name]
        targets = _resolve_targets(hosts, spec)

        async def job(_check=check, _targets=targets):
            await run_once(_targets, [_check], executor, store, sink)

        scheduler.add_job(job, CronTrigger.from_crontab(spec["cron"]),
                          id=f"{name}:{spec.get('hosts')}", max_instances=1)
    return scheduler


async def _amain(config_path: str) -> None:
    cfg = load_config(config_path)
    hosts = load_hosts(cfg.inventory)
    executor = AsyncsshExecutor(connect_timeout=cfg.ssh.connect_timeout)
    store = Store(cfg.sqlite_path)
    sink = AlertSink(webhook=cfg.alerts.webhook, severities=set(cfg.alerts.on))
    scheduler = build_scheduler(cfg, hosts, executor, store, sink)
    scheduler.start()
    print(f"ops-daemon running  ({len(cfg.schedule)} jobs, {len(hosts)} hosts)")
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        scheduler.shutdown(wait=False)
    finally:
        await executor.close()
        store.close()


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    asyncio.run(_amain(config_path))


if __name__ == "__main__":
    main()
