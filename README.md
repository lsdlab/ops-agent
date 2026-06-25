# ops-agent

Centralized Linux ops agent built on `claude-agent-sdk`. One central box runs
the brain + executor; managed machines install nothing (plain SSH targets).

## Architecture

````md
```
central box (1): ops-client (LLM, interactive) + ops-daemon (cron inspections)
        │ SSH (push, key auth)
   ┌────┴────┐
 host-A .. host-N   (sshd + your pubkey only)
```
````

- `ops_core`: inventory, SSH executor, read-only allowlist + danger denylist +
  approval policy, SQLite audit/state, inspections, webhook alerts.
- `ops_mcp`: in-process MCP server exposing 5 tools to the agent.
- `ops_daemon`: scheduled read-only inspections (no LLM); validates every check
  against the allowlist at startup and refuses to start otherwise.
- `ops_client`: claude-agent-sdk loop; read-only tools auto-run, `run_remote`
  always goes through a `can_use_tool` approval gate.

## Setup (central box)

````md
```bash
cd ops-agent
uv venv && uv pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...
cp hosts.yaml.example hosts.yaml   # edit: addresses, users, key, tags
# edit config.yaml                  # set alerts.webhook, schedule, hosts
```
````

Managed Linux machines: ensure `sshd` is running, create the `ops` user, and
add your public key to `~ops/.ssh/authorized_keys`. Nothing else to install.

## Run

````md
```bash
uv run ops-daemon config.yaml    # scheduled inspections + alerts (long-running)
uv run ops-client config.yaml    # interactive chat: "查所有 prod 机器的磁盘"
```
````

## Tests

````md
```bash
uv run pytest -q
# real-SSH integration test (optional, needs a docker sshd target):
# OPS_SSH_INT_TEST=1 OPS_SSH_KEY=/path/key uv run pytest tests/integration/test_remote_exec_ssh.py
```
````
