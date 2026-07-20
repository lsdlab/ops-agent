"""Approval gate for remote command execution.

Policy precedence: danger deny (hard stop) > shell metachar (smuggling risk)
> read-only allowlist (auto-approve) > everything else (requires approval).

Approval cache (LRU, TTL-based):
- Only *approved* decisions are cached — denials are never cached so the user
  gets re-prompted on repeated commands (safety: accidental approvals are not
  silently replayed).
- Default TTL is 60 seconds.  A command approved once auto-runs for the next
  minute.  Dangerous commands (matched by the denylist) are never auto-approved
  regardless of cache state.
"""

from __future__ import annotations
import asyncio
import inspect
import sys
import time
from collections import deque
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from ops_core.allowlist import Allowlist, DangerDenylist
from ops_core.policy import Policy

_REMOTE_TOOL = "run_remote"
_APPROVAL_TIMEOUT = 30  # seconds before auto-deny
_APPROVAL_CACHE_TTL = 60  # seconds for LRU cache
_APPROVAL_CACHE_MAX = 20  # maximum cached entries


def _is_run_remote(tool_name: str) -> bool:
    """Check if the tool name refers to run_remote (exact or SDK-mangled)."""
    return tool_name == _REMOTE_TOOL or tool_name.endswith("__" + _REMOTE_TOOL)


class _ApprovalCache:
    """LRU cache of *approved* commands. Denials are never cached.

    The docstring and return type deliberately differ:
    - check() returns bool | None (True = cached approval, None = miss).
      It never returns False because denials are not cached.
    - The old docstring promised "False if cached deny" which was misleading.
    """

    def __init__(self, ttl: int = _APPROVAL_CACHE_TTL):
        self._ttl = ttl
        self._cache: deque[tuple[str, float]] = deque()

    def check(self, command: str) -> bool | None:
        """Return True if cached approval, None if miss (miss or denial)."""
        now = time.monotonic()
        # Prune expired entries (oldest first)
        while self._cache and now - self._cache[0][1] > self._ttl:
            self._cache.popleft()
        for cmd, _ts in self._cache:
            if cmd == command:
                return True  # cached approval
        return None  # miss (or previously denied, which is not cached)

    def record(self, command: str, approved: bool) -> None:
        """Record an approval decision. Only approvals are cached."""
        if not approved:
            return  # denials are never cached (safety)
        now = time.monotonic()
        self._cache.append((command, now))
        # Keep cache bounded — evict oldest
        while len(self._cache) > _APPROVAL_CACHE_MAX:
            self._cache.popleft()


# Global cache (for terminal use only; tests create per-instance caches).
_GLOBAL_CACHE = _ApprovalCache()


def make_can_use_tool(allowlist: Allowlist, denylist: DangerDenylist, approver,
                      cache: _ApprovalCache | None = None):
    """Build a can_use_tool callback with batch approval + cache.

    Parameters
    ----------
    approver : callable(command: str) -> bool | Coroutine[..., bool, ...]
        For the terminal client this prompts the user; tests inject a plain
        function (e.g. ``lambda c: True``).
    cache : _ApprovalCache | None
        Per-instance cache. Pass ``None`` to use the global cache, or
        ``_ApprovalCache()`` for tests.
    """
    policy = Policy(allowlist, denylist)
    cache = cache or _GLOBAL_CACHE

    async def can_use_tool(tool_name: str, tool_input: dict, context) -> object:
        # Non-run_remote tools are always allowed (read-only MCP tools).
        if not _is_run_remote(tool_name):
            return PermissionResultAllow()

        command = (tool_input or {}).get("command", "")
        if not command:
            return PermissionResultAllow(updated_input=tool_input)

        # Policy decision
        verdict = policy.decide(command, "interactive")
        if verdict.is_deny:
            return PermissionResultDeny(message=verdict.reason or "denied by policy")
        if verdict.is_auto_allow:
            return PermissionResultAllow(updated_input=tool_input)

        # Cache check (only for commands requiring approval)
        cached = cache.check(command)
        if cached is not None:
            if cached:
                return PermissionResultAllow(updated_input=tool_input)
            # Not cached — denials are never recorded, so this branch is
            # technically unreachable. Kept for defensive clarity.
            return PermissionResultDeny(message="previously denied (cached)")

        # Ask the approver (batch or single)
        approved = await _maybe_await(approver, command)
        if approved:
            cache.record(command, True)
            return PermissionResultAllow(updated_input=tool_input)
        return PermissionResultDeny(message="user declined the command")

    return can_use_tool


async def _maybe_await(approver, command: str):
    """Invoke an approver callback, handling sync/async/coroutine objects."""
    result = approver(command)
    if asyncio.iscoroutine(result):
        return await result
    if asyncio.isfuture(result):
        return await result
    # Plain sync callable (lambda, function) — run in executor to avoid
    # blocking the event loop if it does I/O.
    if callable(result):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, result)
    # Already resolved to a bool
    return bool(result)


async def terminal_approver(command: str) -> bool:
    """Async wrapper — runs input() in a thread to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()

    async def _with_timeout():
        def _prompt() -> bool:
            print(f"\n[approval required] remote command:\n  {command}\n",
                  file=sys.stderr)
            while True:
                ans = input("Run this command? [y/N] ").strip().lower()
                if ans in ("y", "yes"):
                    return True
                if ans in ("", "n", "no"):
                    return False
        return await loop.run_in_executor(None, _prompt)

    try:
        return await asyncio.wait_for(_with_timeout(), timeout=_APPROVAL_TIMEOUT)
    except asyncio.TimeoutError:
        print(f"\n[approval timed out after {_APPROVAL_TIMEOUT}s, denied)",
              file=sys.stderr)
        return False
