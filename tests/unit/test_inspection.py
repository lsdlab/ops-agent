import asyncio
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


def test_memory_ok():
    check = BUILTIN_CHECKS["memory_usage"]
    stdout = (
        "              total        used        free      shared  buff/cache   available\n"
        "Mem:        8000000     3000000     1000000      100000     4000000     4500000\n"
    )
    value = check.parse(stdout)
    # used/total = 3.0M/8.0M = 37.5%
    assert value["pct"] == 37.5
    assert check.evaluate(value) is Status.OK


def test_run_check_uses_executor():
    h = Host(alias="web-1", address="a")
    ex = FakeExecutor()
    ex.set(h.alias, "df -P",
           ExecResult(h.alias, "df -P",
                      "FS b U A Cap M\n/dev/sda1 100 90 10 95% /\n", "", 0))
    cr = asyncio.run(run_check(h, BUILTIN_CHECKS["disk_usage"], ex))
    assert cr.host == "web-1"
    assert cr.status is Status.CRIT
