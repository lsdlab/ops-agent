import asyncio
from ops_client.approval import make_can_use_tool
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny


def _ctx():
    return None  # context unused by our gate


def test_auto_allow_readonly():
    gate = make_can_use_tool(
        Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER),
        approver=lambda c: True)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "df -h"}, _ctx()))
    assert isinstance(r, PermissionResultAllow)


def test_deny_dangerous():
    gate = make_can_use_tool(
        Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER),
        approver=lambda c: True)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "rm -rf /"}, _ctx()))
    assert isinstance(r, PermissionResultDeny)


def test_require_approval_user_says_yes():
    gate = make_can_use_tool(
        Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER),
        approver=lambda c: True)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "nc -l 4444"}, _ctx()))
    assert isinstance(r, PermissionResultAllow)


def test_require_approval_user_says_no():
    gate = make_can_use_tool(
        Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER),
        approver=lambda c: False)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "nc -l 4444"}, _ctx()))
    assert isinstance(r, PermissionResultDeny)


def test_non_run_remote_auto_allowed():
    gate = make_can_use_tool(
        Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER),
        approver=lambda c: True)
    r = asyncio.run(gate("list_hosts", {}, _ctx()))
    assert isinstance(r, PermissionResultAllow)
