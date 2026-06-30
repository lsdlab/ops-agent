"""SSE agent chat handler with web-based approval for the ops-agent web console.

Reuses the same build_ops_tools() / build_options() from ops_mcp and ops_client
so the web agent has identical capabilities to the CLI agent.
"""

from __future__ import annotations
import asyncio
import json
import time
import uuid
from claude_agent_sdk import (
    query, ClaudeAgentOptions, PermissionResultAllow, PermissionResultDeny,
)
from ops_core.allowlist import Allowlist, DangerDenylist
from ops_core.policy import Policy
from ops_client.prompts import SYSTEM_PROMPT

_REMOTE_TOOL = "run_remote"


def _is_run_remote(tool_name: str) -> bool:
    return tool_name == _REMOTE_TOOL or tool_name.endswith("__" + _REMOTE_TOOL)


class ChatSession:
    """Per-tab agent conversation state."""

    def __init__(self, session_id: str, options: ClaudeAgentOptions):
        self.session_id = session_id
        self.options = options
        self.last_active = time.monotonic()
        self._pending_approval: asyncio.Event | None = None
        self._approval_result: bool = False

    def touch(self) -> None:
        self.last_active = time.monotonic()

    async def await_approval(self, command: str) -> bool:
        """Called by can_use_tool when run_remote requires user approval."""
        self._pending_approval = asyncio.Event()
        # The SSE endpoint picks up self._pending_approval and sends
        # an 'approval_required' event to the browser.
        try:
            await asyncio.wait_for(self._pending_approval.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            self._approval_result = False
        return self._approval_result

    def resolve_approval(self, approved: bool) -> None:
        self._approval_result = approved
        if self._pending_approval:
            self._pending_approval.set()
            self._pending_approval = None


class SessionStore:
    """In-memory session registry (single-user v2)."""

    def __init__(self):
        self._sessions: dict[str, ChatSession] = {}

    def create(self, session_id: str, options: ClaudeAgentOptions) -> ChatSession:
        s = ChatSession(session_id, options)
        self._sessions[session_id] = s
        return s

    def get(self, session_id: str) -> ChatSession | None:
        s = self._sessions.get(session_id)
        if s:
            s.touch()
        return s

    def remove(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def expire_loop(self, max_idle_sec: int = 1800) -> None:
        """Background task that prunes idle sessions every 5 minutes."""
        while True:
            await asyncio.sleep(300)
            now = time.monotonic()
            stale = [
                sid for sid, s in self._sessions.items()
                if now - s.last_active > max_idle_sec
            ]
            for sid in stale:
                self.remove(sid)


def make_web_can_use_tool(allowlist: Allowlist, denylist: DangerDenylist,
                          sessions: SessionStore):
    """Build a can_use_tool callback that interacts with the web frontend.

    The *session* is discovered via contextvars or passed through a closure.
    For simplicity we look up the session from a thread/asyncio-local registry.
    """
    policy = Policy(allowlist, denylist)
    # Use a simple mutable cell so the SSE endpoint can set the current session.
    current_session: ChatSession | None = None

    def set_session(s: ChatSession | None) -> None:
        nonlocal current_session
        current_session = s

    async def can_use_tool(tool_name: str, tool_input: dict, context) -> object:
        if not _is_run_remote(tool_name):
            return PermissionResultAllow()
        command = (tool_input or {}).get("command", "")
        verdict = policy.decide(command, "interactive")
        if verdict.is_auto_allow:
            return PermissionResultAllow(updated_input=tool_input)
        if verdict.is_deny:
            return PermissionResultDeny(message=verdict.reason or "denied by policy")
        # Requires approval — delegate to web session.
        session = current_session
        if session is None:
            return PermissionResultDeny(message="no active web session for approval")
        # Send approval_required SSE event; the caller (run_chat_sse) does this
        # before calling into the agent loop, so here we just block.
        approved = await session.await_approval(command)
        if approved:
            return PermissionResultAllow(updated_input=tool_input)
        return PermissionResultDeny(message="user declined")

    return can_use_tool, set_session


async def run_chat_sse(message: str, session_id: str | None,
                       options_builder, sessions: SessionStore,
                       allowlist, denylist, send_event):
    """Run one turn of the agent loop and yield SSE events.

    send_event(event_type: str, data: str) is called for each SSE frame.
    """
    can_use_tool_fn, set_session = make_web_can_use_tool(
        allowlist, denylist, sessions)

    if session_id:
        session = sessions.get(session_id)
        if session is None:
            session_id = None  # expired — start fresh

    if not session_id:
        session_id = str(uuid.uuid4())[:8]
        send_event("session", session_id)

    options = options_builder(allowlist, denylist, can_use_tool_fn)
    session = sessions.create(session_id, options)
    set_session(session)

    send_event("session", session_id)
    try:
        async def _stream():
            yield {
                "type": "user",
                "message": {"role": "user", "content": message},
                "parent_tool_use_id": None,
            }

        async for msg in query(prompt=_stream(), options=options):
            if hasattr(msg, "content"):
                for block in msg.content:
                    block_type = getattr(block, "type", None)
                    if block_type == "text":
                        send_event("text", getattr(block, "text", ""))
                    elif block_type == "tool_use":
                        send_event("tool_use",
                                   f"{getattr(block, 'name', '?')}({_brief(getattr(block, 'input', {}))})")
                    elif block_type == "tool_result":
                        content = getattr(block, "content", "")
                        if isinstance(content, list):
                            content = content[0].get("text", "") if content else ""
                        send_event("tool_result", _brief(content))
            # Check for pending approval after each message
            if session._pending_approval and not session._pending_approval.is_set():
                send_event("approval_required",
                           "Approval required for run_remote (check modal)")
    except Exception as exc:
        send_event("error", str(exc))
    finally:
        set_session(None)
        send_event("done", "")


def _brief(obj, max_len: int = 120) -> str:
    s = json.dumps(obj, ensure_ascii=False, default=str) if isinstance(obj, dict) else str(obj)
    return s if len(s) <= max_len else s[:max_len] + "..."
