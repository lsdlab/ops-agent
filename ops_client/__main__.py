"""ops-client: interactive ops agent REPL with prompt_toolkit + rich."""

from __future__ import annotations
import asyncio
import os
import shlex
import sys
import time
from pathlib import Path

# ---- prompt_toolkit ----
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.document import Document

# ---- rich ----
from rich.console import Console
from rich.markdown import Markdown
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live
from rich.layout import Layout
from rich import box

# ---- SDK ----
from claude_agent_sdk import query, ClaudeAgentOptions

# ---- ops internals ----
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
_HISTFILE = Path.home() / ".ops_agent_history"

ALLOWED = [
    "list_hosts", "run_inspection", "get_inspection_history",
    "get_host_facts", "get_inspection_summary", "get_inspection_trend",
    "get_correlated_history",
]
DISALLOWED = ["Bash", "Write", "Edit", "WebFetch", "WebSearch", "Task", "Skill"]

# ---- Colour palette (dark terminal theme) ----
C = {
    "bg":       "#0f1117",
    "surface":  "#161822",
    "border":   "#2a2d3e",
    "accent":   "#5eead4",   # teal
    "accent2":  "#a78bfa",   # purple
    "ok":       "#4ade80",
    "warn":     "#fbbf24",
    "crit":     "#f87171",
    "dim":      "#6b7280",
    "text":     "#e2e8f0",
    "highlight":"#334155",
}

_PROMPT_STYLE = Style.from_dict({
    "prompt":        f"bold {C['accent']}",
    "separator":     C['dim'],
    "bottom-toolbar": f"bg:{C['surface']} {C['dim']}",
    "bottom-toolbar.highlight": f"bg:{C['surface']} {C['accent']}",
    "completion-menu": f"bg:{C['surface']} {C['text']}",
    "completion-menu.completion": f"bg:{C['surface']} {C['text']}",
    "completion-menu.completion.current": f"bg:{C['accent']} #0f1117 bold",
    "auto-suggestion": C['dim'],
})


# ---- Input lexer (syntax highlighting) ----

class OpsLexer(Lexer):
    """Highlight host aliases and slash-commands in user input."""
    def __init__(self):
        self.hosts: set[str] = set()
        self.commands: set[str] = set()

    def lex_document(self, document: Document):
        def _lex(_line_number: int):
            text = document.text
            if text.startswith("/"):
                yield len(text), f"bold {C['accent2']}"
                return
            words = text.split()
            pos = 0
            for w in words:
                idx = text.index(w, pos)
                if idx > pos:
                    yield idx - pos, ""
                if w in self.hosts:
                    yield len(w), f"bold {C['accent']}"
                elif w in self.commands:
                    yield len(w), f"italic {C['accent2']}"
                else:
                    yield len(w), ""
                pos = idx + len(w)
        return _lex


# ---- Completion ----

def _make_completer() -> Completer:
    cmds = ["/help", "/h", "/quit", "/q", "/exit", "/clear", "/c",
            "/history", "/hosts", "/checks", "/config", "/ping",
            "/healthcheck", "/quick", "/qc", "/security"]

    class OpsCompleter(Completer):
        def get_completions(self, document, complete_event):
            text = document.text_before_cursor or ""
            if not text.startswith("/"):
                return
            for cmd in cmds:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text),
                                     display=cmd, display_meta="command")
    return OpsCompleter()


# ---- Key bindings ----

def _make_bindings() -> KeyBindings:
    kb = KeyBindings()
    @kb.add("escape", "enter")
    def _(event):
        event.current_buffer.insert_text("\n")
    @kb.add("c-d")
    def _(event):
        if not event.current_buffer.text:
            event.app.exit(result=None)
    return kb


# ---- Bottom toolbar ----

def _toolbar(hosts, api_ok: bool):
    """Return a formatted toolbar string showing context."""
    host_count = len(hosts)
    host_str = f"hosts:{host_count}" if host_count else "no hosts"
    api_str = f"{C['ok']}●{C['dim']} api" if api_ok else f"{C['crit']}●{C['dim']} api"
    return HTML(
        f"<bottom-toolbar> {api_str}  │  {host_str}  │  "
        f"Ctrl-C:interrupt  Ctrl-D:exit  /help  Tab:complete"
        f" </bottom-toolbar>"
    )


# ---- Output rendering ----

def _render(message) -> None:
    subtype = getattr(message, "subtype", "")
    if subtype and (subtype.startswith("hook_") or subtype == "init"):
        return

    if hasattr(message, "content"):
        for block in message.content:
            # Text
            text = getattr(block, "text", None)
            if text:
                try:
                    console.print(Markdown(text))
                except Exception:
                    console.print(text)
                continue
            # Tool-use
            name = getattr(block, "name", None)
            if name:
                inp = _brief(getattr(block, "input", {}))
                console.print(Panel(
                    f"[bold {C['accent']}]{name}[/] {C['dim']}({inp})[/]",
                    border_style=C['accent'], padding=(0, 1), box=box.ROUNDED))
                continue
            # Tool-result
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
                    body = "\n".join(lines)[:4000]
                    color = C['crit'] if is_error else C['ok']
                    console.print(Panel(body, border_style=color, padding=(0, 1),
                                        box=box.ROUNDED))

    if subtype == "success":
        result = getattr(message, "result", "")
        if result and "Not logged in" in str(result):
            console.print(Panel(
                "[bold red]Not authenticated[/]\n"
                "  export ANTHROPIC_API_KEY=sk-ant-...\n"
                "  or set api.api_key in config.yaml",
                border_style="red"))
        elif result and getattr(message, "is_error", False):
            console.print(Panel(str(result), border_style="red"))


def _brief(obj, max_len=100) -> str:
    s = str(obj)
    return s if len(s) <= max_len else s[:max_len] + "…"


# ---- Slash commands ----

def _show_help():
    t = Table(border_style=f"dim {C['border']}", box=box.ROUNDED,
              show_header=False, padding=(0, 2), title="Commands")
    rows = [
        ("/help, /h",       "Show this help"),
        ("/quit, /q",       "Exit"),
        ("/clear, /c",       "Clear screen"),
        ("/hosts",          "List managed hosts"),
        ("/checks",         "Built-in inspection checks"),
        ("/config",         "Current config"),
        ("/ping [host]",    "Test SSH connectivity"),
        ("/healthcheck [h]","Full health check (8 sections)"),
        ("/quick [h]",      "Quick check (load/mem/disk)"),
        ("/security [h]",   "Security audit"),
        ("/history",        "Command history"),
        ("", ""),
        ("↑/↓",              "Navigate history"),
        ("Ctrl-R",           "Search history"),
        ("Tab",              "Complete /command"),
        ("Ctrl-C",           "Interrupt query"),
        ("Ctrl-D",           "Exit (empty line)"),
    ]
    for key, desc in rows:
        t.add_row(f"[bold {C['accent']}]{key}[/]", f"{C['dim']}{desc}[/]")
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
        "disk_usage": "WARN ≥85%  CRIT ≥92%",
        "disk_inodes": "WARN ≥85%  CRIT ≥92%",
        "memory_usage": "avail<15% WARN  <5% CRIT",
        "swap_usage": "WARN >30%  CRIT >60%",
        "load_avg": "WARN >0.7/core  CRIT >1.0/core",
        "failed_services": "any failed → CRIT",
        "zombie_procs": "WARN ≥5  CRIT ≥20",
    }
    t = Table(border_style=C['border'], box=box.ROUNDED, title="Inspection Checks")
    t.add_column("Check", style=f"bold {C['accent']}")
    t.add_column("Command", style=C['dim'])
    t.add_column("Metric", style=C['accent2'])
    t.add_column("Thresholds", style=C['warn'])
    for name, chk in BUILTIN_CHECKS.items():
        t.add_row(name, chk.command,
                  {"disk_usage": "max_pct", "disk_inodes": "max_inode_pct",
                   "memory_usage": "pct_avail", "swap_usage": "pct",
                   "load_avg": "ratio", "failed_services": "failed",
                   "zombie_procs": "zombies"}.get(name, "—"),
                  th.get(name, "—"))
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


def _show_history(session: PromptSession):
    entries = list(session.history.load_history_strings())
    if not entries:
        console.print(f"[{C['dim']}]No history yet.[/]")
        return
    t = Table(border_style=C['border'], box=box.ROUNDED, show_header=False, padding=(0, 1))
    t.add_column(style=C['dim'], justify="right")
    t.add_column()
    for i, e in enumerate(entries[-50:], 1):
        t.add_row(f"{i:4d}", e[:120])
    console.print(t)


def _handle_slash(line: str, session: PromptSession, hosts) -> tuple[bool, str | None]:
    parts = shlex.split(line)
    if not parts:
        return False, None
    cmd = parts[0].lstrip("/").lower()

    if cmd in ("q", "quit", "exit"):
        console.print(f"[{C['dim']}]bye[/]")
        return True, None
    if cmd in ("h", "help"):
        _show_help(); return False, None
    if cmd in ("clear", "c"):
        console.clear(); return False, None
    if cmd == "history":
        _show_history(session); return False, None
    if cmd == "hosts":
        _show_hosts(hosts) if hosts else console.print(f"[{C['dim']}](no hosts)[/]")
        return False, None
    if cmd == "checks":
        _show_checks(); return False, None
    if cmd == "config":
        _show_config(); return False, None

    # ---- Context-dependent commands ----
    host = parts[1] if len(parts) > 1 else (_pick_host(hosts) if hosts else None)

    if cmd == "ping":
        if not host: return False, None
        return False, (f"Test SSH connectivity to {host}. Run: hostname && uptime && whoami. "
                       "If it fails, report the exact error.")

    if cmd == "healthcheck":
        if not host: return False, None
        return False, HEALTHCHECK_PROMPT.format(host=host)
    if cmd in ("quick", "qc"):
        if not host: return False, None
        return False, QUICK_CHECK_PROMPT.format(host=host)
    if cmd == "security":
        if not host: return False, None
        return False, SECURITY_CHECK_PROMPT.format(host=host)

    console.print(f"[{C['dim']}]Unknown: {cmd}.  Try /help[/]")
    return False, None


def _pick_host(hosts) -> str | None:
    if not hosts:
        console.print(f"[{C['crit']}]No hosts in inventory.[/]"); return None
    if len(hosts) == 1:
        return hosts[0].alias
    aliases = ", ".join(h.alias for h in hosts)
    console.print(f"[{C['dim']}]Multiple hosts: {aliases}[/]")
    console.print(f"[{C['dim']}]Usage: /<cmd> <host>[/]")
    return None


# ---- Agent loop ----

def build_options(hosts, executor, store, allowlist, denylist) -> ClaudeAgentOptions:
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
        max_turns=100,
        env=env_vars,
    )


async def chat(options: ClaudeAgentOptions, hosts: list) -> None:
    lexer = OpsLexer()
    lexer.hosts = {h.alias for h in hosts}
    lexer.commands = {"list_hosts", "run_remote", "run_inspection", "get_host_facts",
                      "get_inspection_history", "get_inspection_summary",
                      "get_inspection_trend", "get_correlated_history"}
    api_ok = bool(os.environ.get("ANTHROPIC_API_KEY") or
                  getattr(options, 'env', {}).get("ANTHROPIC_API_KEY", ""))

    session = PromptSession(
        history=FileHistory(str(_HISTFILE)),
        completer=_make_completer(),
        lexer=lexer,
        style=_PROMPT_STYLE,
        key_bindings=_make_bindings(),
        auto_suggest=AutoSuggestFromHistory(),
        bottom_toolbar=lambda: _toolbar(hosts, api_ok),
        message=HTML(f"<prompt>❯</prompt> "),
    )

    # Welcome
    console.print(Panel(
        f"[bold {C['accent']}]ops-agent[/] {C['dim']}interactive client[/]\n"
        f"{C['dim']}Type /help for commands  ·  Ctrl-C to interrupt  ·  "
        f"Ctrl-D to exit[/]",
        border_style=C['accent'], box=box.ROUNDED, padding=(1, 2)))
    console.print()

    while True:
        try:
            prompt = await session.prompt_async()
        except (EOFError, KeyboardInterrupt):
            console.print(f"\n[{C['dim']}]bye[/]")
            return
        if prompt is None:
            continue
        prompt = prompt.strip()
        if not prompt:
            continue

        # Slash commands
        if prompt.startswith("/"):
            try:
                should_exit, injected = _handle_slash(prompt, session, hosts)
                if should_exit:
                    return
                if injected:
                    prompt = injected
                else:
                    continue
            except Exception as exc:
                console.print(f"[{C['crit']}]{exc}[/]")
                continue

        # Agent query
        async def _stream():
            yield {
                "type": "user",
                "message": {"role": "user", "content": prompt},
                "parent_tool_use_id": None,
            }

        t0 = time.monotonic()
        try:
            async for message in query(prompt=_stream(), options=options):
                _render(message)
        except KeyboardInterrupt:
            console.print(f"\n[{C['dim']}]interrupted[/]")
            continue
        except Exception as exc:
            console.print(f"\n[{C['crit']}]Error: {exc}[/]")

        elapsed = time.monotonic() - t0
        if elapsed > 1:
            console.print(f"[{C['dim']}]({elapsed:.1f}s)[/]")


async def _amain(config_path: str) -> None:
    cfg = load_config(config_path)
    apply_api_env(cfg.api)
    hosts = load_hosts(cfg.inventory)
    executor = AsyncsshExecutor(connect_timeout=cfg.ssh.connect_timeout)
    store = Store(cfg.sqlite_path)
    options = build_options(hosts, executor, store,
                            Allowlist(DEFAULT_READONLY), DangerDenylist(DEFAULT_DANGER))
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
