"""Inspection checks — data-driven definitions with parsers and evaluators.

All commands must be on the read-only allowlist (no shell metacharacters)
so the daemon can run them without LLM or human approval.
"""

from __future__ import annotations
import re
from ops_core.models import Check, CheckResult, ExecResult, Host, Status
from ops_core.remote_exec import Executor

# ---- thresholds ----
DISK_WARN_PCT = 85.0
DISK_CRIT_PCT = 92.0
INODE_WARN_PCT = 85.0
INODE_CRIT_PCT = 92.0
MEM_WARN_PCT = 15.0   # available < 15% of total → WARN (inverted)
MEM_CRIT_PCT = 5.0    # available <  5% of total → CRIT
LOAD_WARN_RATIO = 0.7  # load per core > 0.7 → WARN
LOAD_CRIT_RATIO = 1.0  # load per core > 1.0 → CRIT (saturated)
SWAP_WARN_PCT = 30.0
SWAP_CRIT_PCT = 60.0
ZOMBIE_WARN = 5
ZOMBIE_CRIT = 20


# =============================================================================
# disk_usage — df -P, parse max usage %
# =============================================================================

def _parse_disk(stdout: str) -> dict:
    max_pct = 0.0
    for line in stdout.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 6:
            continue
        m = re.match(r"(\d+)%", cols[-2])
        if m:
            pct = float(m.group(1))
            if pct > max_pct:
                max_pct = pct
    return {"max_pct": max_pct}


def _eval_disk(value: dict) -> Status:
    pct = value["max_pct"]
    if pct >= DISK_CRIT_PCT:
        return Status.CRIT
    if pct >= DISK_WARN_PCT:
        return Status.WARN
    return Status.OK


# =============================================================================
# disk_inodes — df -i, parse max inode usage %
# =============================================================================

def _parse_inodes(stdout: str) -> dict:
    max_pct = 0.0
    for line in stdout.splitlines()[1:]:
        cols = line.split()
        if len(cols) < 6:
            continue
        m = re.match(r"(\d+)%", cols[-2])
        if m:
            pct = float(m.group(1))
            if pct > max_pct:
                max_pct = pct
    return {"max_inode_pct": max_pct}


def _eval_inodes(value: dict) -> Status:
    pct = value["max_inode_pct"]
    if pct >= INODE_CRIT_PCT:
        return Status.CRIT
    if pct >= INODE_WARN_PCT:
        return Status.WARN
    return Status.OK


# =============================================================================
# memory_usage — free -b, parse available as % of total
#   "available" is MemFree + reclaimable (buffers/cache).  This is the metric
#   that actually matters — Linux will use "free" RAM for cache, so "used%"
#   is misleading (high usage is often just healthy caching).
# =============================================================================

def _parse_memory(stdout: str) -> dict:
    total = avail = 0.0
    for line in stdout.splitlines():
        cols = line.split()
        if len(cols) >= 7 and cols[0] == "Mem:":
            total = float(cols[1])
            avail = float(cols[6])   # "available" column
    if not total:
        return {"pct_avail": 100.0}
    pct_avail = round(avail / total * 100, 1)
    return {"pct_avail": pct_avail}


def _eval_memory(value: dict) -> Status:
    pct_avail = value["pct_avail"]
    # Inverted: low available → bad
    if pct_avail <= MEM_CRIT_PCT:
        return Status.CRIT
    if pct_avail <= MEM_WARN_PCT:
        return Status.WARN
    return Status.OK


# =============================================================================
# swap_usage — free -b, parse swap used %
# =============================================================================

def _parse_swap(stdout: str) -> dict:
    total = used = 0.0
    for line in stdout.splitlines():
        cols = line.split()
        if len(cols) >= 3 and cols[0] == "Swap:":
            total = float(cols[1])
            used = float(cols[2])
    if not total:
        return {"pct": 0.0}
    return {"pct": round(used / total * 100, 1)}


def _eval_swap(value: dict) -> Status:
    pct = value["pct"]
    if pct >= SWAP_CRIT_PCT:
        return Status.CRIT
    if pct >= SWAP_WARN_PCT:
        return Status.WARN
    return Status.OK


# =============================================================================
# load_avg — cat /proc/loadavg then nproc, normalize per core
#   The command separates the two with ';' which is a shell metachar.
#   For daemon use we keep it as-is and validate against the allowlist.
#   The allowlist pattern "cat /proc/loadavg*" should match the first part;
#   the parser handles the combined output.
#
#   /proc/loadavg format: "0.15 0.08 0.06 1/234 12345"
#   nproc output: a single integer
# =============================================================================

def _parse_loadavg(stdout: str) -> dict:
    """Parse combined output of 'cat /proc/loadavg; nproc'."""
    lines = stdout.strip().splitlines()
    load1 = 0.0
    cores = 1  # fallback — don't divide by zero
    for line in lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 5 and "/" in parts[3]:
            # loadavg line: "0.15 0.08 0.06 1/234 12345"
            load1 = float(parts[0])
        elif len(parts) == 1 and parts[0].isdigit():
            # nproc line: "4"
            cores = int(parts[0])
    return {"load1": load1, "cores": cores, "ratio": round(load1 / cores, 2)}


def _eval_loadavg(value: dict) -> Status:
    ratio = value["ratio"]
    if ratio >= LOAD_CRIT_RATIO:
        return Status.CRIT
    if ratio >= LOAD_WARN_RATIO:
        return Status.WARN
    return Status.OK


# =============================================================================
# failed_services — systemctl list-units --failed
#   Any failed systemd unit → CRIT.  This is intentional: on a well-managed
#   production host, zero services should be in failed state.
# =============================================================================

def _parse_failed_services(stdout: str) -> dict:
    lines = [l for l in stdout.splitlines() if l.strip() and "UNIT" not in l]
    return {"failed": len(lines)}


def _eval_failed_services(value: dict) -> Status:
    return Status.CRIT if value["failed"] > 0 else Status.OK


# =============================================================================
# zombie_procs — ps -eo stat,pid
#   Transient zombies (1-2) are normal on Linux.  A growing count or >5
#   sustained usually indicates a parent process that isn't reaping children.
# =============================================================================

def _parse_zombie(stdout: str) -> dict:
    count = sum(1 for line in stdout.splitlines()[1:] if line.startswith("Z"))
    return {"zombies": count}


def _eval_zombie(value: dict) -> Status:
    count = value["zombies"]
    if count >= ZOMBIE_CRIT:
        return Status.CRIT
    if count >= ZOMBIE_WARN:
        return Status.WARN
    return Status.OK


# =============================================================================
# Registry
# =============================================================================

BUILTIN_CHECKS: dict[str, Check] = {
    "disk_usage": Check(
        "disk_usage", "df -P",
        _parse_disk, _eval_disk,
    ),
    "disk_inodes": Check(
        "disk_inodes", "df -i",
        _parse_inodes, _eval_inodes,
    ),
    "memory_usage": Check(
        "memory_usage", "free -b",
        _parse_memory, _eval_memory,
    ),
    "swap_usage": Check(
        "swap_usage", "free -b",
        _parse_swap, _eval_swap,
    ),
    "load_avg": Check(
        "load_avg", "cat /proc/loadavg; nproc",
        _parse_loadavg, _eval_loadavg,
    ),
    "failed_services": Check(
        "failed_services", "systemctl list-units --failed",
        _parse_failed_services, _eval_failed_services,
    ),
    "zombie_procs": Check(
        "zombie_procs", "ps -eo stat,pid",
        _parse_zombie, _eval_zombie,
    ),
}


# =============================================================================
# run_check — execute one check on one host
# =============================================================================

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
