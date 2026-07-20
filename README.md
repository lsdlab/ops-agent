# ops-agent

Centralized Linux ops agent built on `claude-agent-sdk`. One central box runs
the brain + executor; managed machines install nothing (plain SSH targets).

## Architecture

```
central box (1): ops-client (LLM REPL) + ops-web (console) + ops-daemon (cron inspections)
        │ SSH (push, key auth)
   ┌────┴────┐
 host-A .. host-N   (sshd + your pubkey only; provisioned once via ops-bootstrap)
```

- `ops_core`: inventory, async SSH executor, read-only allowlist + danger
  denylist + approval policy, SQLite audit/state, inspections, webhook alerts,
  and pure formatting helpers (`analysis.py`) that render store results into
  LLM-friendly text.
- `ops_mcp`: in-process MCP server exposing **11 tools** to the agent
  (`list_hosts`, `run_remote`, `run_inspection`, `get_inspection_history`,
  `get_inspection_summary`, `get_inspection_trend`, `get_correlated_history`,
  `get_host_facts`, `list_checks`, `query_audit`, `query_alerts`).
- `ops_daemon`: scheduled read-only inspections (no LLM); validates every check
  against the allowlist at startup and refuses to start otherwise.
- `ops_client`: `claude-agent-sdk` REPL loop; read-only tools auto-run,
  `run_remote` always goes through a `can_use_tool` approval gate.
- `ops_web`: Starlette web console — dashboard, host list/detail with 7-day
  trends, inspections, audit log, and an SSE-streaming chat that reuses the
  same MCP server + approval gate as the REPL.
- `ops_bootstrap`: one-shot provisioning of managed machines over SSH — creates
  the `ops` user, installs your public key, and writes a scoped sudoers snippet.

## Setup (central box)

```bash
cd ops-agent
uv venv && uv pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...
cp hosts.yaml.example hosts.yaml   # edit: addresses, users, key, tags
# edit config.yaml                  # set alerts.webhook, schedule, hosts
```

Managed Linux machines: ensure `sshd` is running, then provision them with
`ops-bootstrap` (below) — or manually create the `ops` user and add your public
key to `~ops/.ssh/authorized_keys`. Nothing else to install.

## Run

```bash
uv run ops-daemon config.yaml                       # scheduled inspections + alerts (long-running)
uv run ops-client config.yaml                       # interactive REPL: "查所有 prod 机器的磁盘"
uv run ops-web config.yaml                          # web console on http://0.0.0.0:8080
uv run ops-bootstrap config.yaml --tag prod         # one-shot: provision prod hosts (creates ops user + key + sudoers)
uv run ops-bootstrap config.yaml --dry-run          # preview provisioning without changing anything
```

## Tests

```bash
uv run pytest -q
# real-SSH integration test (optional, needs a docker sshd target):
# OPS_SSH_INT_TEST=1 OPS_SSH_KEY=/path/key uv run pytest tests/integration/test_remote_exec_ssh.py
```
