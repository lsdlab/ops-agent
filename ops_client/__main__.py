from __future__ import annotations
import asyncio
import sys
from claude_agent_sdk import query, ClaudeAgentOptions
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.config import load_config
from ops_core.inventory import load_hosts
from ops_core.remote_exec import AsyncsshExecutor
from ops_core.store import Store
from ops_mcp.server import build_server
from ops_client.approval import make_can_use_tool, terminal_approver
from ops_client.prompts import SYSTEM_PROMPT

# Read-only tools auto-run; run_remote is intentionally omitted so it always
# reaches the can_use_tool approval gate.
ALLOWED = ["list_hosts", "run_inspection", "get_inspection_history", "get_host_facts"]
DISALLOWED = ["Bash", "Write", "Edit", "MultiEdit", "WebFetch", "WebSearch",
              "Task", "Skill"]


def build_options(hosts, executor, store, allowlist, denylist) -> ClaudeAgentOptions:
    server = build_server(hosts=hosts, executor=executor, store=store)
    can_use_tool = make_can_use_tool(allowlist, denylist, terminal_approver)
    return ClaudeAgentOptions(
        mcp_servers={"ops": server},
        allowed_tools=ALLOWED,
        disallowed_tools=DISALLOWED,
        can_use_tool=can_use_tool,
        permission_mode="default",
        system_prompt=SYSTEM_PROMPT,
        max_turns=40,
    )


async def chat(options: ClaudeAgentOptions) -> None:
    print("ops-agent interactive client. Ctrl-D to exit.", file=sys.stderr)
    while True:
        try:
            prompt = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            print("\nbye", file=sys.stderr)
            return
        prompt = prompt.strip()
        if not prompt:
            continue
        async for message in query(prompt=prompt, options=options):
            _render(message)


def _render(message) -> None:
    # Messages are dict-like blocks from the SDK; render text/assistant content.
    if hasattr(message, "content"):
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                print(text)
    else:
        print(message)


async def _amain(config_path: str) -> None:
    cfg = load_config(config_path)
    hosts = load_hosts(cfg.inventory)
    executor = AsyncsshExecutor(connect_timeout=cfg.ssh.exec_timeout)
    store = Store(cfg.sqlite_path)
    options = build_options(hosts, executor, store,
                            Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER))
    try:
        await chat(options)
    finally:
        await executor.close()
        store.close()


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    asyncio.run(_amain(config_path))


if __name__ == "__main__":
    main()
