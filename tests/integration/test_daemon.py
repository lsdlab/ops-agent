import asyncio
from ops_daemon.__main__ import validate_checks, run_once
from ops_core.models import Host, ExecResult, Status
from ops_core.remote_exec import FakeExecutor
from ops_core.store import Store
from ops_core.alerting import AlertSink
from ops_core.inspection import BUILTIN_CHECKS


def test_validate_checks_passes_for_builtin():
    problems = validate_checks(list(BUILTIN_CHECKS.values()))
    assert problems == []


def test_validate_checks_rejects_non_allowlisted():
    bad = BUILTIN_CHECKS["disk_usage"].__class__(
        "evil", "nc -l 4444", lambda s: {}, lambda v: Status.OK)
    problems = validate_checks([bad])
    assert any("evil" in p for p in problems)


def test_run_once_writes_results_and_alerts(tmp_path, capfd):
    h = Host(alias="web-1", address="a")
    ex = FakeExecutor()
    ex.set("web-1", "df -P",
           ExecResult("web-1", "df -P",
                      "FS b U A C M\n/dev/sda1 100 95 5 95% /\n", "", 0))
    store = Store(tmp_path / "t.db")
    sink = AlertSink(webhook=None, severities={"warn", "crit"})
    asyncio.run(run_once([h], [BUILTIN_CHECKS["disk_usage"]], ex, store, sink,
                         run_id="r1"))
    rows = store.query_inspection(host="web-1", check_name="disk_usage")
    assert len(rows) == 1
    assert rows[0]["status"] == "crit"
    out = capfd.readouterr().out
    assert "disk_usage" in out  # alert logged
