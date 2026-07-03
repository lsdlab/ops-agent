from __future__ import annotations
import asyncio
import sys
import time
from collections import deque
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from ops_core.allowlist import Allowlist, DangerDenylist
from ops_core.policy import Policy

_REMOTE_TOOL = "run_remote"
_APPROVAL_TIMEOUT = 30  # seconds before auto-deny
_APPROVAL_CACHE_TTL = 60  # seconds for LRU cache


def _is_run_remote(tool_name: str) -> bool:
    return tool_name == _REMOTE_TOOL or tool_name.endswith("__" + _REMOTE_TOOL)


class _ApprovalCache:
    """LRU cache: recent approvals auto-approve within TTL."""

    def __init__(self, ttl: int = _APPROVAL_CACHE_TTL):
        self._ttl = ttl
        self._cache: deque[tuple[str, float]] = deque()

    def check(self, command: str) -> bool | None:
        """Return True if cached approval, False if cached deny, None if miss."""
        now = time.monotonic()
        # Prune expired entries
        while self._cache and now - self._cache[0][1] > self._ttl:
            self._cache.popleft()
        for cmd, ts in self._cache:
            if cmd == command:
                return True  # cached approval
        return None  # miss

    def record(self, command: str, approved: bool) -> None:
        """Record an approval decision."""
        if approved:
            # Only cache approvals
            now = time.monotonic()
            self._cache.append((command, now))
            # Keep cache bounded
            while len(self._cache) > 20:
                self._cache.popleft()


class _ApprovalQueue:
    """Accumulate pending approvals; user approves/denies in batch."""

    def __init__(self):
        self._pending: list[str] = []
        self._result: asyncio.Event = asyncio.Event()
        self._decision: bool | None = None

    def enqueue(self, command: str) -> asyncio.Future[bool]:
        """Queue a command for approval. Returns a Future that resolves when batch is decided."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        future = loop.create_future()
        self._pending.append(command)
        # If this is the first pending, signal the batch approver
        if len(self._pending) == 1:
            self._result.set()
        return future

    async def wait_batch(self) -> bool:
        """Wait for user to decide on the batch, then apply to all."""
        await self._result.wait()
        # If decision was already made (e.g., by tests or programmatic override), skip prompt
        if self._decision is not None:
            # Record in cache
            for cmd in self._pending:
                _GLOBAL_CACHE.record(cmd, bool(self._decision))
            self._pending.clear()
            return bool(self._decision)

        # Show batch
        if len(self._pending) == 1:
            print(f"\n[approval required] remote command:\n  {self._pending[0]}\n", file=sys.stderr)
        else:
            print(f"\n[{len(self._pending)} pending approvals]:\n", file=sys.stderr)
            for i, cmd in enumerate(self._pending, 1):
                print(f"  {i}. {cmd}\n", file=sys.stderr)
        print("  [a] approve all  [d] deny all  [n] none  (timeout {}s)\n".format(
            _APPROVAL_TIMEOUT), file=sys.stderr)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        async def _timeout():
            await asyncio.sleep(_APPROVAL_TIMEOUT)
            if not self._result.done():
                self._decision = False
                self._result.set()

        timeout_task = asyncio.create_task(_timeout())

        def _prompt() -> None:
            while True:
                try:
                    ans = input("[approve all / deny all / none] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    self._decision = False
                    self._result.set()
                    return
                if ans in ("a", "yes", "y", "all", "approve"):
                    self._decision = True
                    break
                if ans in ("d", "no", "n", "none", "deny"):
                    self._decision = False
                    break

        await loop.run_in_executor(None, _prompt)
        timeout_task.cancel()
        try:
            await timeout_task
        except asyncio.CancelledError:
            pass

        # Record in cache
        for cmd in self._pending:
            _GLOBAL_CACHE.record(cmd, bool(self._decision))
        self._pending.clear()
        return bool(self._decision)


# Global instances (for terminal use only; tests create per-instance caches)
_GLOBAL_CACHE = _ApprovalCache()
_GLOBAL_QUEUE = _ApprovalQueue()


def make_can_use_tool(allowlist: Allowlist, denylist: DangerDenylist, approver,
                      cache: _ApprovalCache | None = None):
    """Build a can_use_tool callback with batch approval + cache.

    approver: callable(command:str) -> bool. For the terminal client it prompts
    the user; tests inject a plain function.
    cache: per-instance cache (use None for global, or pass _ApprovalCache() for tests).
    """
    policy = Policy(allowlist, denylist)
    cache = cache or _GLOBAL_CACHE

    async def can_use_tool(tool_name: str, tool_input: dict, context) -> object:
        if not _is_run_remote(tool_name):
            return PermissionResultAllow()
        command = (tool_input or {}).get("command", "")
        if not command:
            return PermissionResultAllow(updated_input=tool_input)
        verdict = policy.decide(command, "interactive")
        if verdict.is_auto_allow:
            return PermissionResultAllow(updated_input=tool_input)
        if verdict.is_deny:
            return PermissionResultDeny(message=verdict.reason or "denied by policy")

        # Check cache first
        cached = cache.check(command)
        if cached is not None:
            if cached:
                return PermissionResultAllow(updated_input=tool_input)
            return PermissionResultDeny(message="previously denied (cached)")

        # Use the approver (batch or single)
        approved = await _maybe_await(approver(command))
        if approved:
            cache.record(command, True)
            return PermissionResultAllow(updated_input=tool_input)
        cache.record(command, False)
        return PermissionResultDeny(message="user declined the command")

    return can_use_tool


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    if callable(value):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, value)
    return value


async def terminal_approver(command: str) -> bool:
    """Async wrapper — runs input() in a thread to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()

    async def _with_timeout():
        def _prompt() -> bool:
            print(f"\n[approval required] remote command:\n  {command}\n", file=sys.stderr)
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
        print(f"\n[approval timed out after {_APPROVAL_TIMEOUT}s, denied)", file=sys.stderr)
        return False
