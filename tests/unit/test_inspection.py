import asyncio
import pytest
from ops_core.models import Host, ExecResult, Status
from ops_core.remote_exec import FakeExecutor
from ops_core.inspection import BUILTIN_CHECKS, run_check


def test_disk_parse_and_threshold():
    check = BUILTIN_CHECKS["disk_usage"]
    stdout = (
        "Filesystem     1024-blocks    Used Available Capacity Mounted on\n"
        "/dev/sda1        50000000 45000000   5000000      95% /\n"
        "/dev/sda2        50000000 10000000  40000000      20% /home\n"
    )
    value = check.parse(stdout)
    assert value["max_pct"] == 95.0
    assert check.evaluate(value) is Status.CRIT


def test_disk_inodes_ok():
    check = BUILTIN_CHECKS["disk_inodes"]
    stdout = (
        "Filesystem     Inodes  IUsed  IFree IUse% Mounted on\n"
        "/dev/sda1      500000  50000  450000   10% /\n"
    )
    value = check.parse(stdout)
    assert value["max_inode_pct"] == 10.0
    assert check.evaluate(value) is Status.OK


def test_memory_available_ok():
    """Memory check now uses 'available' column, not 'used/total'."""
    check = BUILTIN_CHECKS["memory_usage"]
    # total=8000000, available=5600000 → pct_avail = 70%
    stdout = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:        8000000     2000000     4000000      100000     2000000     5600000\n"
    )
    value = check.parse(stdout)
    assert value["pct_avail"] == 70.0
    assert check.evaluate(value) is Status.OK


def test_memory_low_crit():
    check = BUILTIN_CHECKS["memory_usage"]
    # total=8000000, available=300000 → pct_avail = 3.75%
    stdout = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:        8000000     7500000      100000      100000      400000      300000\n"
    )
    value = check.parse(stdout)
    assert value["pct_avail"] == 3.8
    assert check.evaluate(value) is Status.CRIT


def test_swap_parse():
    check = BUILTIN_CHECKS["swap_usage"]
    stdout = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:        8000000     3000000     1000000      100000     4000000     4500000\n"
        "Swap:       4000000     2000000     2000000\n"
    )
    value = check.parse(stdout)
    assert value["pct"] == 50.0
    assert check.evaluate(value) is Status.WARN


def test_load_avg_per_core():
    check = BUILTIN_CHECKS["load_avg"]
    stdout = "4.20 3.50 2.80 1/234 12345\n8\n"
    value = check.parse(stdout)
    assert value["load1"] == 4.2
    assert value["cores"] == 8
    assert value["ratio"] == 0.53   # round(4.2/8, 2) = 0.53
    assert check.evaluate(value) is Status.OK


def test_load_avg_crit():
    check = BUILTIN_CHECKS["load_avg"]
    stdout = "4.2 3.5 2.8 1/100 999\n4\n"
    value = check.parse(stdout)
    assert value["ratio"] == 1.05   # round(4.2/4, 2) = 1.05
    assert check.evaluate(value) is Status.CRIT


def test_zombie_thresholds():
    check = BUILTIN_CHECKS["zombie_procs"]
    assert check.evaluate({"zombies": 0}) is Status.OK
    assert check.evaluate({"zombies": 3}) is Status.OK
    assert check.evaluate({"zombies": 5}) is Status.WARN
    assert check.evaluate({"zombies": 20}) is Status.CRIT


def test_run_check_uses_executor():
    h = Host(alias="web-1", address="a")
    ex = FakeExecutor()
    ex.set(h.alias, "df -P",
           ExecResult(h.alias, "df -P",
                      "FS b U A Cap M\n/dev/sda1 100 90 10 95% /\n", "", 0))
    cr = asyncio.run(run_check(h, BUILTIN_CHECKS["disk_usage"], ex))
    assert cr.host == "web-1"
    assert cr.status is Status.CRIT
