import asyncio
import pytest
from ops_core.models import Host, ExecResult
from ops_core.remote_exec import FakeExecutor, fan_out


def test_fake_executor_returns_canned():
    ex = FakeExecutor()
    h = Host(alias="web-1", address="a")
    ex.set(h.alias, "uptime", ExecResult(h.alias, "uptime", "up 1 day", "", 0))
    out = asyncio.run(ex.run(h, "uptime"))
    assert out.stdout == "up 1 day"
    assert out.rc == 0


def test_fake_executor_missing_raises():
    ex = FakeExecutor()
    h = Host(alias="x", address="a")
    with pytest.raises(KeyError):
        asyncio.run(ex.run(h, "uptime"))


def test_fan_out_runs_all():
    ex = FakeExecutor()
    hosts = [Host(alias=f"h{i}", address="a") for i in range(3)]
    for h in hosts:
        ex.set(h.alias, "uptime", ExecResult(h.alias, "uptime", "ok", "", 0))
    results = asyncio.run(fan_out(ex, hosts, "uptime", concurrency=2))
    assert {r.host for r in results} == {h.alias for h in hosts}
    assert all(r.rc == 0 for r in results)


def test_fan_out_isolates_failure():
    ex = FakeExecutor()
    h_ok = Host(alias="ok", address="a")
    h_bad = Host(alias="bad", address="a")
    ex.set(h_ok.alias, "uptime", ExecResult(h_ok.alias, "uptime", "ok", "", 0))
    # h_bad has no canned entry -> KeyError captured as a failed ExecResult
    results = asyncio.run(fan_out(ex, [h_ok, h_bad], "uptime"))
    by_host = {r.host: r for r in results}
    assert by_host["ok"].rc == 0
    assert by_host["bad"].rc != 0
    assert "error" in by_host["bad"].stderr.lower()
