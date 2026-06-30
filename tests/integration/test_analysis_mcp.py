"""Integration tests for the new v2 MCP analysis tools."""
import asyncio
from ops_core.models import Host, ExecResult, Status
from ops_core.remote_exec import FakeExecutor
from ops_core.store import Store
from ops_mcp.server import build_ops_tools


def _setup(tmp_path, extra_data=True):
    hosts = [Host(alias="web-1", address="a", tags=["web"]),
             Host(alias="db-1", address="b", tags=["db"])]
    ex = FakeExecutor()
    store = Store(tmp_path / "t.db")
    # Populate some inspection history for query tools.
    store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                            status=Status.WARN, value={"max_pct": 88.0},
                            raw_stdout="/dev/sda1 88%")
    store.insert_inspection(run_id="r1", host="web-1", check_name="memory_usage",
                            status=Status.OK, value={"pct": 42.0})
    if extra_data:
        store.insert_inspection(run_id="r2", host="web-1", check_name="disk_usage",
                                status=Status.CRIT, value={"max_pct": 95.0})
        store.insert_inspection(run_id="r2", host="db-1", check_name="disk_usage",
                                status=Status.OK, value={"max_pct": 30.0})
    tools = build_ops_tools(hosts=hosts, executor=ex, store=store)
    return tools


def _by_name(tools, name):
    return next(t for t in tools if t.name == name)


def test_get_inspection_summary(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "get_inspection_summary").handler({}))
    text = out["content"][0]["text"]
    assert "Total inspections: 4" in text
    assert "CRIT: 1" in text


def test_get_inspection_summary_with_host_filter(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "get_inspection_summary").handler(
        {"host": "db-1"}))
    text = out["content"][0]["text"]
    assert "Total inspections: 1" in text
    assert "db-1" not in text  # summary doesn't show host names, just counts


def test_get_inspection_trend(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "get_inspection_trend").handler(
        {"host": "web-1", "check": "disk_usage", "metric": "max_pct",
         "days": 365}))
    text = out["content"][0]["text"]
    assert "web-1 / disk_usage / max_pct" in text
    assert "88.0" in text
    assert "95.0" in text


def test_get_correlated_history(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "get_correlated_history").handler(
        {"run_id": "r1"}))
    text = out["content"][0]["text"]
    assert "run r1" in text
    assert "web-1" in text
    assert "disk_usage=warn" in text
    assert "memory_usage=ok" in text


def test_get_correlated_history_all(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "get_correlated_history").handler({}))
    text = out["content"][0]["text"]
    assert "run r1" in text
    assert "run r2" in text


def test_empty_trend(tmp_path):
    tools = _setup(tmp_path, extra_data=False)
    out = asyncio.run(_by_name(tools, "get_inspection_trend").handler(
        {"host": "no-such", "check": "disk_usage", "metric": "max_pct"}))
    text = out["content"][0]["text"]
    assert "No trend data" in text
