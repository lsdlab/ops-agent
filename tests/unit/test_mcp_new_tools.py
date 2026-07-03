"""Tests for new MCP tools and input validation in ops_mcp/server.py."""
import asyncio
import json
import os
import pathlib
import tempfile
from ops_mcp.server import (
    build_ops_tools, _text,
    ListChecksInput, AuditQueryInput, AlertQueryInput,
)
from ops_core.models import Host, Status
from ops_core.store import Store
from ops_core.remote_exec import FakeExecutor
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny


def _hosts():
    return [Host(alias="web-1", address="10.0.0.1"),
            Host(alias="web-2", address="10.0.0.2")]


def _executor():
    return FakeExecutor()


def _store():
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return Store(pathlib.Path(path), check_same_thread=False)


def _get_tool_names(tools):
    """Get tool names from SdkMcpTool objects."""
    return [t.name for t in tools]


def _get_tool_by_name(tools, name):
    """Get a tool function by name from SdkMcpTool objects."""
    for t in tools:
        if t.name == name:
            return t.handler
    return None


def _text_success():
    result = _text("hello")
    assert result == {"content": [{"type": "text", "text": "hello"}]}
    assert "is_error" not in result


def _text_error():
    result = _text("error msg", is_error=True)
    assert result["is_error"] is True


# ---- Tool registration ----

def test_all_tools_registered():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    names = _get_tool_names(tools)
    expected = [
        "list_hosts", "run_remote", "run_inspection", "get_inspection_history",
        "get_host_facts", "get_inspection_summary", "get_inspection_trend",
        "get_correlated_history", "list_checks", "query_audit", "query_alerts",
    ]
    for name in expected:
        assert name in names, f"Missing tool: {name}"
    assert len(tools) == len(expected)
    store.close()


# ---- list_checks ----

def test_list_checks_returns_all():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "list_checks")
    result = asyncio.run(tool({}))
    body = result["content"][0]["text"]
    assert "disk_usage" in body
    assert "memory_usage" in body
    assert "load_avg" in body
    store.close()


# ---- query_audit ----

def test_query_audit_empty():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "query_audit")
    result = asyncio.run(tool({}))
    assert "no audit" in result["content"][0]["text"].lower()
    store.close()


def test_query_audit_with_data():
    store = _store()
    store.insert_audit(host="web-1", command="df -h", rc=0,
                       initiated_by="agent", approved_by="auto",
                       verdict="auto_allow", stdout_excerpt="out",
                       stderr_excerpt="")
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "query_audit")
    result = asyncio.run(tool({}))
    body = json.loads(result["content"][0]["text"])
    assert len(body) >= 1
    assert body[0]["host"] == "web-1"
    store.close()


def test_query_audit_filtered_by_host():
    store = _store()
    store.insert_audit(host="web-1", command="df -h", rc=0,
                       initiated_by="agent", approved_by="auto",
                       verdict="auto_allow", stdout_excerpt="", stderr_excerpt="")
    store.insert_audit(host="web-2", command="free -h", rc=0,
                       initiated_by="agent", approved_by="auto",
                       verdict="auto_allow", stdout_excerpt="", stderr_excerpt="")
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "query_audit")
    result = asyncio.run(tool({"host": "web-1"}))
    body = json.loads(result["content"][0]["text"])
    assert all(r["host"] == "web-1" for r in body)
    store.close()


# ---- query_alerts ----

def test_query_alerts_empty():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "query_alerts")
    result = asyncio.run(tool({}))
    assert "no alert" in result["content"][0]["text"].lower()
    store.close()


def test_query_alerts_with_data():
    store = _store()
    store.insert_alert(host="web-1", check_name="disk_usage", status=Status.CRIT,
                       value={"max_pct": 95.0}, raw_stdout="df output")
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "query_alerts")
    result = asyncio.run(tool({}))
    body = json.loads(result["content"][0]["text"])
    assert len(body) >= 1
    store.close()


def test_query_alerts_filtered_by_status():
    store = _store()
    store.insert_alert(host="web-1", check_name="disk_usage", status=Status.CRIT,
                       value={"max_pct": 95.0}, raw_stdout="")
    store.insert_alert(host="web-1", check_name="memory_usage", status=Status.OK,
                       value={"pct_avail": 50.0}, raw_stdout="")
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "query_alerts")
    result = asyncio.run(tool({"status": "crit"}))
    body = json.loads(result["content"][0]["text"])
    assert all(r["status"] == "crit" for r in body)
    store.close()


# ---- Input validation ----

def test_run_remote_missing_command():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "run_remote")
    result = asyncio.run(tool({"hosts": ["web-1"]}))
    assert result.get("is_error") is True
    assert "missing required field: command" in result["content"][0]["text"]
    store.close()


def test_run_remote_missing_hosts():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "run_remote")
    result = asyncio.run(tool({"command": "df -h"}))
    assert result.get("is_error") is True
    assert "missing required field: hosts" in result["content"][0]["text"]
    store.close()


def test_run_remote_unknown_host():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "run_remote")
    result = asyncio.run(tool({"hosts": ["unknown"], "command": "df -h"}))
    assert result.get("is_error") is True
    assert "unknown host" in result["content"][0]["text"]
    store.close()


def test_run_inspection_missing_checks():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "run_inspection")
    result = asyncio.run(tool({"hosts": ["web-1"]}))
    assert result.get("is_error") is True
    assert "missing required field: checks" in result["content"][0]["text"]
    store.close()


def test_run_inspection_unknown_check():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "run_inspection")
    result = asyncio.run(tool({"hosts": ["web-1"], "checks": ["nonexistent"]}))
    assert result.get("is_error") is True
    assert "unknown check" in result["content"][0]["text"]
    store.close()


def test_get_inspection_trend_missing_fields():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "get_inspection_trend")
    # Missing host
    result = asyncio.run(tool({"check": "disk_usage", "metric": "max_pct"}))
    assert result.get("is_error") is True
    # Missing check
    result = asyncio.run(tool({"host": "web-1", "metric": "max_pct"}))
    assert result.get("is_error") is True
    # Missing metric
    result = asyncio.run(tool({"host": "web-1", "check": "disk_usage"}))
    assert result.get("is_error") is True
    store.close()


def test_get_inspection_trend_unknown_check():
    store = _store()
    tools = build_ops_tools(hosts=_hosts(), executor=_executor(), store=store,
                            allowlist=Allowlist(DEFAULT_READONLY),
                            denylist=DangerDenylist(DEFAULT_DANGER))
    tool = _get_tool_by_name(tools, "get_inspection_trend")
    result = asyncio.run(tool({"host": "web-1", "check": "nonexistent", "metric": "x"}))
    assert result.get("is_error") is True
    store.close()
