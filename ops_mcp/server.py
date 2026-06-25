from __future__ import annotations
import json
from typing import TypedDict
from claude_agent_sdk import tool, create_sdk_mcp_server, McpSdkServerConfig
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.inventory import filter_hosts
from ops_core.models import Host
from ops_core.policy import Policy
from ops_core.remote_exec import Executor, fan_out
from ops_core.inspection import BUILTIN_CHECKS, run_check
from ops_core.store import Store


class ListHostsInput(TypedDict, total=False):
    tag: str
    alias: str


class RunRemoteInput(TypedDict):
    hosts: list
    command: str


class RunInspectionInput(TypedDict):
    hosts: list
    checks: list


class HistoryInput(TypedDict, total=False):
    host: str
    check: str


class FactsInput(TypedDict):
    host: str


def _text(body: str, is_error: bool = False) -> dict:
    out = {"content": [{"type": "text", "text": body}]}
    if is_error:
        out["is_error"] = True
    return out


def build_ops_tools(*, hosts: list[Host], executor: Executor, store: Store,
                    allowlist: Allowlist | None = None,
                    denylist: DangerDenylist | None = None) -> list:
    allowlist = allowlist or Allowlist(DEFAULT_READONLY)
    denylist = denylist or DangerDenylist(DEFAULT_DANGER)
    policy = Policy(allowlist, denylist)
    by_alias = {h.alias: h for h in hosts}

    @tool("list_hosts", "List managed hosts, optionally filtered by tag/alias",
          ListHostsInput)
    async def list_hosts(args):
        tag = args.get("tag")
        alias = args.get("alias")
        matched = filter_hosts(hosts, tag=tag, alias=alias)
        body = "\n".join(f"{h.alias} {h.address} tags={h.tags}" for h in matched) \
            or "(no hosts)"
        return _text(body)

    @tool("run_remote", "Run a shell command on remote hosts over SSH "
          "(read-only commands auto-run; others require approval)",
          RunRemoteInput)
    async def run_remote(args):
        command = args["command"]
        targets = [by_alias[a] for a in args["hosts"] if a in by_alias]
        verdict = policy.decide(command, "interactive")
        results = await fan_out(executor, targets, command)
        for r in results:
            store.insert_audit(
                host=r.host, command=command, rc=r.rc,
                initiated_by="agent",
                approved_by="auto" if verdict.is_auto_allow else "user",
                verdict=verdict.decision.value,
                stdout_excerpt=r.stdout, stderr_excerpt=r.stderr,
            )
        lines = [f"--- {r.host} (rc={r.rc}) ---\n{r.stdout}{r.stderr}"
                 for r in results]
        return _text("\n\n".join(lines) or "(no results)")

    @tool("run_inspection", "Run read-only inspection checks on hosts",
          RunInspectionInput)
    async def run_inspection(args):
        checks = [BUILTIN_CHECKS[c] for c in args["checks"] if c in BUILTIN_CHECKS]
        targets = [by_alias[a] for a in args["hosts"] if a in by_alias]
        rows = []
        for h in targets:
            for chk in checks:
                cr = await run_check(h, chk, executor)
                rows.append({"host": cr.host, "check": cr.check_name,
                             "status": cr.status.value, "value": cr.value})
        return _text(json.dumps(rows, ensure_ascii=False, indent=2))

    @tool("get_inspection_history", "Get recent inspection results for a host",
          HistoryInput)
    async def get_inspection_history(args):
        rows = store.query_inspection(host=args["host"],
                                      check_name=args.get("check"))
        if not rows:
            return _text("no inspection history")
        return _text(json.dumps(rows, ensure_ascii=False, indent=2,
                                default=str))

    @tool("get_host_facts", "Get cached facts for a host", FactsInput)
    async def get_host_facts(args):
        h = by_alias.get(args["host"])
        if h is None:
            return _text(f"unknown host: {args['host']}", is_error=True)
        return _text(json.dumps(
            {"alias": h.alias, "address": h.address, "port": h.port,
             "user": h.user, "tags": h.tags},
            ensure_ascii=False, indent=2))

    return [list_hosts, run_remote, run_inspection, get_inspection_history,
            get_host_facts]


def build_server(*, hosts: list[Host], executor: Executor, store: Store,
                 name: str = "ops") -> McpSdkServerConfig:
    tools = build_ops_tools(hosts=hosts, executor=executor, store=store)
    return create_sdk_mcp_server(name=name, tools=tools)
