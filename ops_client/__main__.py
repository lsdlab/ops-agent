"""ops-client: interactive ops agent REPL with rich output + readline input.

Uses stdlib readline for reliable input (history, line editing, tab completion)
and rich for beautiful output rendering.
"""

from __future__ import annotations
import asyncio
import atexit
import os
import readline
import shlex
import sys
import time
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box

from claude_agent_sdk import query, ClaudeAgentOptions

from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.config import load_config, apply_api_env
from ops_core.inventory import load_hosts
from ops_core.remote_exec import AsyncsshExecutor
from ops_core.store import Store
from ops_mcp.server import build_server
from ops_client.approval import make_can_use_tool, terminal_approver
from ops_client.prompts import (
    SYSTEM_PROMPT, HEALTHCHECK_PROMPT, QUICK_CHECK_PROMPT, SECURITY_CHECK_PROMPT,
)

console = Console()
_HISTFILE = os.path.expanduser("~/.ops_agent_history")
_RST = "\033[0m"

ALLOWED = [
    "list_hosts", "run_inspection", "get_inspection_history",
    "get_host_facts", "get_inspection_summary", "get_inspection_trend",
    "get_correlated_history", "list_checks", "query_audit", "query_alerts",
]
DISALLOWED = ["Bash", "Write", "Edit", "WebFetch", "WebSearch", "Task", "Skill"]

C = {
    "bg":       "#0f1117",
    "surface":  "#161822",
    "border":   "#2a2d3e",
    "accent":   "#5eead4",
    "accent2":  "#a78bfa",
    "ok":       "#4ade80",
    "warn":     "#fbbf24",
    "crit":     "#f87171",
    "dim":      "#6b7280",
}

# ---- Rich Text helpers ----

def _t(text: str, style: str = "") -> Text:
    return Text(text, style=style)

def _dim(text: str) -> Text:      return Text(text, style=C['dim'])
def _accent(text: str) -> Text:   return Text(text, style=f"bold {C['accent']}")
def _crit(text: str) -> Text:    return Text(text, style=f"bold {C['crit']}")

# ---- readline setup ----

_SLASH_CMDS = ["help", "h", "quit", "q", "exit", "clear", "c",
               "history", "hosts", "checks", "config", "ping",
               "healthcheck", "quick", "qc", "security",
               "retry", "r", "audit", "alerts", "listchecks"]

def _init_readline(hosts: list | None = None):
    try:
        readline.read_history_file(_HISTFILE)
    except FileNotFoundError:
        pass
    atexit.register(readline.write_history_file, _HISTFILE)
    readline.set_history_length(1000)
    _readline_hosts = hosts
    readline.set_completer(lambda text, state: _readline_completer(text, state, _readline_hosts))
    readline.parse_and_bind("tab: complete")
    readline.parse_and_bind("set colored-completion-prefix on")
    readline.parse_and_bind("set colored-stats on")

def _readline_completer(text: str, state: int, hosts: list | None = None) -> str | None:
    if text.startswith("/"):
        matches = [f"/{c}" for c in _SLASH_CMDS if f"/{c}".startswith(text)]
        if state < len(matches):
            return matches[state]
    # Tab-complete host aliases for slash commands that take a host
    if hosts and not text.startswith("/"):
        # After a slash command, e.g. "/healthcheck 210"
        parts = text.rsplit(" ", 1)
        if len(parts) == 2 and parts[0].startswith("/"):
            cmd = parts[0].lstrip("/").lower()
            host_cmds = {"ping", "healthcheck", "quick", "qc", "security",
                         "audit", "alerts"}
            if cmd in host_cmds:
                matches = [h.alias for h in hosts if h.alias.startswith(parts[1])]
                if state < len(matches):
                    return parts[0] + " " + matches[state]
    return None

# ---- Output rendering ----

def _render(message) -> None:
    subtype = getattr(message, "subtype", "")
    if subtype and (subtype.startswith("hook_") or subtype == "init"):
        return

    if hasattr(message, "content"):
        for block in message.content:
            text = getattr(block, "text", None)
            if text:
                try:
                    console.print(Markdown(text))
                except (ValueError, RuntimeError):
                    console.print(text)
                continue
            name = getattr(block, "name", None)
            if name:
                inp = _brief(getattr(block, "input", {}))
                console.print(Panel(Text.assemble(
                    (name, f"bold {C['accent']}"),
                    (f" ({inp})", C['dim'])),
                    border_style=C['accent'], padding=(0, 1), box=box.ROUNDED))
                continue
            content = getattr(block, "content", None)
            if content is not None:
                is_error = getattr(block, "is_error", False)
                lines = []
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            lines.append(c.get("text", ""))
                elif content:
                    lines.append(str(content))
                if lines:
                    color = C['crit'] if is_error else C['ok']
                    body = _truncate_output(lines)
                    console.print(Panel(body,
                                        border_style=color, padding=(0, 1),
                                        box=box.ROUNDED))

    if subtype == "success":
        result = getattr(message, "result", "")
        if result and "Not logged in" in str(result):
            console.print(Panel(
                "Not authenticated.\n  export ANTHROPIC_API_KEY=sk-ant-...\n"
                "  or set api.api_key in config.yaml", border_style="red"))
        elif result and getattr(message, "is_error", False):
            console.print(Panel(str(result), border_style="red"))


def _truncate_output(lines: list[str]) -> str:
    """Truncate output at line boundaries with a warning indicator."""
    MAX_LINES = 120
    MAX_TOTAL = 8000
    if len(lines) <= MAX_LINES:
        full = "\n".join(lines)
        if len(full) <= MAX_TOTAL:
            return full
        # Within line limit but too many chars — truncate at boundary
        char_count = 0
        cut = 0
        for i, line in enumerate(lines):
            if char_count + len(line) > MAX_TOTAL:
                break
            char_count += len(line) + 1
            cut = i + 1
        result = "\n".join(lines[:cut])
        return result + f"\n[truncated: {len(lines) - cut} more lines]"
    first = "\n".join(lines[:MAX_LINES])
    return first + f"\n[truncated: {len(lines) - MAX_LINES} more lines]"


def _brief(obj, max_len=100) -> str:
    s = str(obj)
    return s if len(s) <= max_len else s[:max_len] + "…"


# ---- Slash commands ----

def _show_help():
    t = Table(border_style=C['border'], box=box.ROUNDED,
              show_header=False, padding=(0, 2), title="Commands")
    rows = [
        ("/help /h",         "Show this help"),
        ("/quit /q",         "Exit (double-confirm)"),
        ("/clear /c",        "Clear screen"),
        ("/retry /r",        "Re-run last query"),
        ("/hosts",           "List managed hosts"),
        ("/checks",          "Built-in inspection checks"),
        ("/listchecks",      "List available check names"),
        ("/config",          "Current config"),
        ("/audit [h]",       "Query command audit log"),
        ("/alerts [h]",      "Query alert history"),
        ("/ping [h]",        "Test SSH connectivity"),
        ("/healthcheck [h]", "Full health check (8 sections)"),
        ("/quick [h]",       "Quick check (load/mem/disk)"),
        ("/security [h]",    "Security audit"),
        ("/history",         "Command history"),
        ("", ""),
        ("↑/↓",   "Navigate history"),
        ("Ctrl-R",            "Search history"),
        ("Tab",               "Complete /command or host alias"),
        ("Ctrl-C",            "Interrupt query"),
        ("Ctrl-D",            "Exit"),
    ]
    for key, desc in rows:
        t.add_row(_accent(key), _dim(desc))
    console.print(t)


def _show_hosts(hosts):
    t = Table(border_style=C['border'], box=box.ROUNDED, title="Managed Hosts")
    t.add_column("Alias", style=f"bold {C['accent']}")
    t.add_column("Address")
    t.add_column("Port", justify="right")
    t.add_column("User", style=C['dim'])
    t.add_column("Tags", style=C['accent2'])
    for h in hosts:
        t.add_row(h.alias, h.address, str(h.port), h.user, ", ".join(h.tags))
    console.print(t)


def _show_checks():
    from ops_core.inspection import BUILTIN_CHECKS
    th = {
        "disk_usage": "max_pct ≥85% WARN  ≥92% CRIT",
        "disk_inodes": "max_inode_pct ≥85% WARN  ≥92% CRIT",
        "memory_usage": "pct_avail <15% WARN  <5% CRIT",
        "swap_usage": "pct >30% WARN  >60% CRIT",
        "load_avg": "ratio >0.7 WARN  >1.0 CRIT",
        "failed_services": "failed >0 → CRIT",
        "zombie_procs": "zombies ≥5 WARN  ≥20 CRIT",
    }
    metrics = {"disk_usage": "max_pct", "disk_inodes": "max_inode_pct",
               "memory_usage": "pct_avail", "swap_usage": "pct",
               "load_avg": "ratio", "failed_services": "failed",
               "zombie_procs": "zombies"}
    t = Table(border_style=C['border'], box=box.ROUNDED, title="Inspection Checks")
    t.add_column("Check", style=f"bold {C['accent']}")
    t.add_column("Command", style=C['dim'])
    t.add_column("Metric", style=C['accent2'])
    t.add_column("Thresholds", style=C['warn'])
    for name, chk in BUILTIN_CHECKS.items():
        t.add_row(name, chk.command, metrics.get(name, "—"), th.get(name, "—"))
    console.print(t)


def _show_config():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    cfg = load_config(cfg_path)
    t = Table(border_style=C['border'], box=box.ROUNDED, title=f"Config ({cfg_path})",
              show_header=False, padding=(0, 2))
    t.add_column(style="bold")
    t.add_column()
    t.add_row("inventory",       cfg.inventory)
    t.add_row("sqlite",          cfg.sqlite_path)
    t.add_row("concurrency",     str(cfg.concurrency))
    t.add_row("ssh timeout",     f"connect={cfg.ssh.connect_timeout}s exec={cfg.ssh.exec_timeout}s")
    has_wb = "✓" if cfg.alerts.webhook else "✗"
    t.add_row("alerts",          f"webhook={has_wb}  on={cfg.alerts.on}")
    t.add_row("schedule",        f"{len(cfg.schedule)} job(s)")
    has_key = "✓" if cfg.api.api_key or os.environ.get("ANTHROPIC_API_KEY") else "✗"
    t.add_row("api key",         has_key)
    base = cfg.api.base_url or os.environ.get("ANTHROPIC_BASE_URL", "(default)")
    t.add_row("api base_url",    base)
    console.print(t)


def _show_history():
    try:
        hl = readline.get_current_history_length()
        for i in range(1, hl + 1):
            entry = readline.get_history_item(i)
            console.print(Text(f"  {i:4d}  {entry}", style=C['dim']))
    except Exception:
        console.print(_dim("No history yet."))


# ---- Slash commands (host-required) ----
_HOST_CMDS = {"ping", "healthcheck", "quick", "qc", "security"}


def _handle_slash(line: str, hosts) -> tuple[bool, str | None]:
    parts = shlex.split(line)
    if not parts:
        return False, None
    cmd = parts[0].lstrip("/").lower()

    if cmd in ("q", "quit", "exit"):
        # Confirm exit only if there's history
        try:
            hl = readline.get_current_history_length()
        except Exception:
            hl = 0
        if hl > 0:
            console.print(_crit("Exit? Type /quit again to confirm, or Ctrl-C to cancel."))
            return False, None  # require double-confirm
        console.print(_dim("bye"))
        return True, None

    if cmd in ("h", "help"):
        _show_help(); return False, None
    if cmd in ("clear", "c"):
        console.clear(); return False, None
    if cmd == "history":
        _show_history(); return False, None
    if cmd == "hosts":
        _show_hosts(hosts) if hosts else console.print(_dim("(no hosts)"))
        return False, None
    if cmd == "checks":
        _show_checks(); return False, None
    if cmd == "config":
        _show_config(); return False, None
    if cmd in ("retry", "r"):
        return False, "_RETRY_"  # special marker handled in chat()
    if cmd == "audit":
        host = parts[1] if len(parts) > 1 else None
        if host:
            return False, f"Run query_audit with host={host!r} to show command audit log."
        return False, "Run query_audit to show recent command audit log."
    if cmd == "alerts":
        host = parts[1] if len(parts) > 1 else None
        if host:
            return False, f"Run query_alerts with host={host!r} to show alert history."
        return False, "Run query_alerts to show recent alert history."
    if cmd == "listchecks":
        return False, "Run list_checks to show all available inspection checks."

    if cmd in _HOST_CMDS:
        host = parts[1] if len(parts) > 1 else (_pick_host(hosts) if hosts else None)
        if not host:
            console.print(_crit(f"/{cmd} requires a host. Available: "
                                f"{', '.join(h.alias for h in hosts)}"))
            return False, None
        if cmd == "ping":
            return False, (f"Test SSH connectivity to {host}. Run: hostname && uptime && whoami. "
                           "If it fails, report the exact error.")
        if cmd == "healthcheck":
            return False, HEALTHCHECK_PROMPT.format(host=host)
        if cmd in ("quick", "qc"):
            return False, QUICK_CHECK_PROMPT.format(host=host)
        if cmd == "security":
            return False, SECURITY_CHECK_PROMPT.format(host=host)

    # Unknown command — list similar ones
    console.print(_crit(f"Unknown command: /{cmd}"))
    if _SLASH_CMDS:
        similar = [c for c in _SLASH_CMDS if _levenshtein(cmd, c) <= 2]
        if similar:
            console.print(_dim(f"Did you mean: {', '.join('/' + s for s in similar)}?"))
        else:
            console.print(_dim(f"Try /help for available commands."))
    return False, None


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance for fuzzy command matching."""
    if len(a) > len(b):
        a, b = b, a
    costs = list(range(len(a) + 1))
    for i, ca in enumerate(a):
        new_costs = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            new_costs.append(min(costs[j + 1] + 1, new_costs[j] + 1, costs[j] + cost))
        costs = new_costs
    return costs[-1]


def _pick_host(hosts) -> str | None:
    if not hosts:
        console.print(_crit("No hosts in inventory.")); return None
    if len(hosts) == 1:
        return hosts[0].alias
    aliases = ", ".join(h.alias for h in hosts)
    console.print(_dim(f"Multiple hosts: {aliases}"))
    console.print(_dim("Usage: /<cmd> <host>"))
    return None


# ---- Agent loop ----

async def _make_stream(prompt: str):
    yield {
        "type": "user",
        "message": {"role": "user", "content": prompt},
        "parent_tool_use_id": None,
    }

def build_options(hosts, executor, store, allowlist, denylist, max_turns: int = 100) -> ClaudeAgentOptions:
    server = build_server(hosts=hosts, executor=executor, store=store)
    can_use_tool = make_can_use_tool(allowlist, denylist, terminal_approver)
    env_vars = {}
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
        val = os.environ.get(var)
        if val:
            env_vars[var] = val
    return ClaudeAgentOptions(
        mcp_servers={"ops": server},
        allowed_tools=ALLOWED,
        disallowed_tools=DISALLOWED,
        can_use_tool=can_use_tool,
        permission_mode="default",
        system_prompt=SYSTEM_PROMPT,
        max_turns=max_turns,
        env=env_vars,
    )


async def chat(options: ClaudeAgentOptions, hosts: list) -> None:
    welcome = Text("\nops-agent  ", style=f"bold {C['accent']}")
    welcome.append("interactive client\n", style=C['dim'])
    welcome.append("/help  ", style=C['accent'])
    welcome.append("for commands  ·  ", style=C['dim'])
    welcome.append("Ctrl-C", style="bold")
    welcome.append(" to interrupt  ·  ", style=C['dim'])
    welcome.append("Ctrl-D", style="bold")
    welcome.append(" to exit", style=C['dim'])
    console.print(Panel(welcome, border_style=C['accent'], box=box.ROUNDED, padding=(1, 2)))
    console.print(Text(
        f"  ↑↓ navigate  Tab complete /command  Ctrl-R search history{_RST}",
        style=C['dim']))
    print()

    last_prompt: str | None = None

    while True:
        try:
            prompt = input("\033[1m\033[36m❯\033[0m ")
        except EOFError:
            console.print(_dim("\nbye"))
            return
        except KeyboardInterrupt:
            console.print(_dim("\n(interrupted — type /quit to exit)"))
            continue
        prompt = prompt.strip()
        if not prompt:
            continue

        # Slash commands
        if prompt.startswith("/"):
            try:
                should_exit, injected = _handle_slash(prompt, hosts)
                if should_exit:
                    return
                if injected == "_RETRY_":
                    if last_prompt:
                        console.print(_dim(f"Retrying: {last_prompt[:80]}{'...' if len(last_prompt) > 80 else ''}"))
                        prompt = last_prompt
                    else:
                        console.print(_crit("No previous prompt to retry."))
                        continue
                elif injected:
                    prompt = injected
                else:
                    continue
            except Exception as exc:
                console.print(_crit(str(exc)))
                continue

        # Input length limit
        if len(prompt) > 10000:
            console.print(_crit(f"Input too long ({len(prompt)} chars). Max 10000."))
            continue

        # Show loading indicator
        console.print(_dim("⋯ thinking..."))

        t0 = time.monotonic()
        try:
            async for message in query(
                prompt=_make_stream(prompt), options=options
            ):
                _render(message)
            last_prompt = prompt
        except KeyboardInterrupt:
            console.print(_dim("\ninterrupted"))
            continue
        except Exception as exc:
            console.print(_crit(f"\nError: {exc}"))

        elapsed = time.monotonic() - t0
        console.print(Text(f"({elapsed:.1f}s)", style=C['dim']))


async def _amain(config_path: str) -> None:
    cfg = load_config(config_path)
    apply_api_env(cfg.api)
    hosts = load_hosts(cfg.inventory)
    _init_readline(hosts)
    executor = AsyncsshExecutor(connect_timeout=cfg.ssh.connect_timeout)
    store = Store(cfg.sqlite_path)
    options = build_options(
        hosts, executor, store,
        Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER),
        max_turns=100,
    )
    try:
        await chat(options, hosts)
    finally:
        await executor.close()
        store.close()


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    asyncio.run(_amain(config_path))


if __name__ == "__main__":
    main()
