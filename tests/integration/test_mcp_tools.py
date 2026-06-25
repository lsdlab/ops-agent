import asyncio
from ops_core.models import Host, ExecResult, Status
from ops_core.remote_exec import FakeExecutor
from ops_core.store import Store
from ops_mcp.server import build_ops_tools


def _setup(tmp_path):
    hosts = [Host(alias="web-1", address="a", tags=["web"])]
    ex = FakeExecutor()
    ex.set("web-1", "uptime", ExecResult("web-1", "uptime", "up 1 day", "", 0))
    ex.set("web-1", "df -P",
           ExecResult("web-1", "df -P",
                      "FS b U A C M\n/dev/sda1 100 90 10 95% /\n", "", 0))
    store = Store(tmp_path / "t.db")
    tools = build_ops_tools(hosts=hosts, executor=ex, store=store)
    return tools


def _by_name(tools, name):
    return next(t for t in tools if t.name == name)


def test_list_hosts(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "list_hosts").handler({"tag": "web"}))
    assert "web-1" in out["content"][0]["text"]


def test_run_remote(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "run_remote").handler(
        {"hosts": ["web-1"], "command": "uptime"}))
    text = out["content"][0]["text"]
    assert "web-1" in text and "up 1 day" in text


def test_run_remote_writes_audit(tmp_path):
    tools = _setup(tmp_path)
    asyncio.run(_by_name(tools, "run_remote").handler(
        {"hosts": ["web-1"], "command": "uptime"}))
    store = Store(tmp_path / "t.db")
    assert len(store.query_audit(host="web-1")) == 1


def test_get_inspection_history_empty(tmp_path):
    tools = _setup(tmp_path)
    out = asyncio.run(_by_name(tools, "get_inspection_history").handler(
        {"host": "web-1"}))
    assert "no" in out["content"][0]["text"].lower() or "[" in out["content"][0]["text"]
