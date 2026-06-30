from __future__ import annotations
import asyncio
import sys
from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny
from ops_core.allowlist import Allowlist, DangerDenylist
from ops_core.policy import Policy

_REMOTE_TOOL = "run_remote"


def _is_run_remote(tool_name: str) -> bool:
    return tool_name == _REMOTE_TOOL or tool_name.endswith("__" + _REMOTE_TOOL)


def make_can_use_tool(allowlist: Allowlist, denylist: DangerDenylist, approver):
    """Build a can_use_tool callback.

    approver: callable(command:str) -> bool. For the terminal client it prompts
    the user; tests inject a plain function.
    """
    policy = Policy(allowlist, denylist)

    async def can_use_tool(tool_name: str, tool_input: dict, context) -> object:
        if not _is_run_remote(tool_name):
            return PermissionResultAllow()
        command = (tool_input or {}).get("command", "")
        verdict = policy.decide(command, "interactive")
        if verdict.is_auto_allow:
            return PermissionResultAllow(updated_input=tool_input)
        if verdict.is_deny:
            return PermissionResultDeny(message=verdict.reason or "denied by policy")
        # require approval
        approved = await _maybe_await(approver(command))
        if approved:
            return PermissionResultAllow(updated_input=tool_input)
        return PermissionResultDeny(message="user declined the command")

    return can_use_tool


async def _maybe_await(value):
    if asyncio.iscoroutine(value):
        return await value
    if callable(value):
        # Run sync callables in a thread so blocking input() doesn't stall the
        # event loop while the SDK waits for the approval decision.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, value)
    return value


async def terminal_approver(command: str) -> bool:
    """Async wrapper — runs input() in a thread to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()

    def _prompt() -> bool:
        print(f"\n[approval required] remote command:\n  {command}\n", file=sys.stderr)
        while True:
            ans = input("Run this command? [y/N] ").strip().lower()
            if ans in ("y", "yes"):
                return True
            if ans in ("", "n", "no"):
                return False

    return await loop.run_in_executor(None, _prompt)
