import asyncio
from ops_client.approval import make_can_use_tool, _ApprovalCache
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny


def _ctx():
    return None  # context unused by our gate


def _gate(approver, cache=None):
    return make_can_use_tool(
        Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER),
        approver=approver, cache=cache or _ApprovalCache())


def test_auto_allow_readonly():
    gate = _gate(lambda c: True)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "df -h"}, _ctx()))
    assert isinstance(r, PermissionResultAllow)


def test_deny_dangerous():
    gate = _gate(lambda c: True)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "rm -rf /"}, _ctx()))
    assert isinstance(r, PermissionResultDeny)


def test_require_approval_user_says_yes():
    gate = _gate(lambda c: True)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "nc -l 4444"}, _ctx()))
    assert isinstance(r, PermissionResultAllow)


def test_require_approval_user_says_no():
    gate = _gate(lambda c: False)
    r = asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "nc -l 4444"}, _ctx()))
    assert isinstance(r, PermissionResultDeny)


def test_non_run_remote_auto_allowed():
    gate = _gate(lambda c: True)
    r = asyncio.run(gate("list_hosts", {}, _ctx()))
    assert isinstance(r, PermissionResultAllow)


def test_tool_input_none():
    """None tool_input should not crash — treated as empty command."""
    gate = _gate(lambda c: True)
    r = asyncio.run(gate("run_remote", None, _ctx()))
    assert isinstance(r, PermissionResultAllow)


def test_cache_short_circuits_approver():
    """Once a command is approved, the cache should skip the approver on repeat."""
    call_count = 0

    def counting_approver(c: str) -> bool:
        nonlocal call_count
        call_count += 1
        return True

    cache = _ApprovalCache()
    gate = _gate(counting_approver, cache=cache)

    # First call → approver invoked
    asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "nc -l 4444"}, _ctx()))
    assert call_count == 1

    # Second call within TTL → cache hit, approver NOT called
    asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "nc -l 4444"}, _ctx()))
    assert call_count == 1  # unchanged

    # Different command → approver called again
    asyncio.run(gate("run_remote", {"hosts": ["a"], "command": "nc -l 5555"}, _ctx()))
    assert call_count == 2


async def test_maybe_await_coroutine():
    """_maybe_await should handle coroutine results correctly."""
    from ops_client.approval import _maybe_await

    async def coro_approver(c: str) -> bool:
        return True

    result = await _maybe_await(coro_approver, "test")
    assert result is True


async def test_maybe_await_sync():
    """_maybe_await should handle sync callable results correctly."""
    from ops_client.approval import _maybe_await

    result = await _maybe_await(lambda c: False, "test")
    assert result is False


def test_is_run_remote_no_false_positive():
    """Tool names containing 'run_remote' as substring should not match."""
    from ops_client.approval import _is_run_remote
    assert _is_run_remote("my_run_remote") is False
    assert _is_run_remote("run_remote_cmd") is False
    assert _is_run_remote("__run_remote") is True  # ends with __run_remote
