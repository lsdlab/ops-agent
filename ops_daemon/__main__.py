from __future__ import annotations
import asyncio
import sys
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
    run_id = run_id or str(uuid.uuid4())
    for h in hosts:
        for chk in checks:
            cr = await run_check(h, chk, executor)
            store.insert_inspection(run_id=run_id, host=cr.host,
                                    check_name=cr.check_name, status=cr.status,
                                    value=cr.value)
            await sink.send(cr)


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
    print("ops-daemon running", file=sys.stderr)
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
