from __future__ import annotations
import re
from ops_core.models import Check, CheckResult, ExecResult, Host, Status
from ops_core.remote_exec import Executor

DISK_WARN = 85.0
DISK_CRIT = 92.0
MEM_WARN = 85.0
MEM_CRIT = 95.0


def _parse_disk(stdout: str) -> dict:
    max_pct = 0.0
    for line in stdout.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 6:
            continue
        m = re.match(r"(\d+)%", cols[-2])
        if m:
            max_pct = max(max_pct, float(m.group(1)))
    return {"max_pct": max_pct}


def _eval_disk(value: dict) -> Status:
    pct = value["max_pct"]
    if pct >= DISK_CRIT:
        return Status.CRIT
    if pct >= DISK_WARN:
        return Status.WARN
    return Status.OK


def _parse_memory(stdout: str) -> dict:
    total = used = None
    for line in stdout.splitlines():
        cols = line.split()
        if len(cols) >= 3 and cols[0] == "Mem:":
            total = float(cols[1])
            used = float(cols[2])
    if not total:
        return {"pct": 0.0}
    return {"pct": round(used / total * 100, 1)}


def _eval_memory(value: dict) -> Status:
    pct = value["pct"]
    if pct >= MEM_CRIT:
        return Status.CRIT
    if pct >= MEM_WARN:
        return Status.WARN
    return Status.OK


def _parse_loadavg(stdout: str) -> dict:
    # /proc/loadavg layout: "0.00 0.01 0.05 1/123 12345" — only the 1-min load
    # is meaningful here; cpu count is not available without a second command.
    parts = stdout.split()
    load1 = float(parts[0]) if parts else 0.0
    return {"load1": load1}


def _eval_loadavg(value: dict) -> Status:
    # Absolute 1-min load thresholds (per-core normalization is a v2 refinement).
    load1 = value["load1"]
    if load1 >= 4.0:
        return Status.CRIT
    if load1 >= 2.0:
        return Status.WARN
    return Status.OK


def _parse_failed_services(stdout: str) -> dict:
    lines = [l for l in stdout.splitlines() if l.strip() and "UNIT" not in l]
    return {"failed": len(lines)}


def _eval_failed_services(value: dict) -> Status:
    return Status.CRIT if value["failed"] > 0 else Status.OK


def _parse_zombie(stdout: str) -> dict:
    count = sum(1 for line in stdout.splitlines()[1:] if line.startswith("Z"))
    return {"zombies": count}


def _eval_zombie(value: dict) -> Status:
    return Status.WARN if value["zombies"] > 0 else Status.OK


BUILTIN_CHECKS: dict[str, Check] = {
    "disk_usage": Check("disk_usage", "df -P", _parse_disk, _eval_disk),
    "memory_usage": Check("memory_usage", "free -b", _parse_memory, _eval_memory),
    "load_avg": Check("load_avg", "cat /proc/loadavg", _parse_loadavg, _eval_loadavg),
    "failed_services": Check(
        "failed_services", "systemctl list-units --failed",
        _parse_failed_services, _eval_failed_services,
    ),
    "zombie_procs": Check(
        "zombie_procs", "ps -eo stat,pid", _parse_zombie, _eval_zombie,
    ),
}


async def run_check(host: Host, check: Check, executor: Executor,
                    timeout: float = 30.0) -> CheckResult:
    result: ExecResult = await executor.run(host, check.command, timeout=timeout)
    if result.rc != 0:
        return CheckResult(host=host.alias, check_name=check.name,
                           status=Status.CRIT, value={"rc": result.rc,
                                                       "stderr": result.stderr},
                           raw=result.stdout)
    value = check.parse(result.stdout)
    return CheckResult(host=host.alias, check_name=check.name,
                       status=check.evaluate(value), value=value,
                       raw=result.stdout)
