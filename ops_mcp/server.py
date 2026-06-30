from __future__ import annotations
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict
from claude_agent_sdk import tool, create_sdk_mcp_server, McpSdkServerConfig
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.inventory import filter_hosts
from ops_core.models import Host
from ops_core.policy import Policy
from ops_core.remote_exec import Executor, fan_out
from ops_core.inspection import BUILTIN_CHECKS, run_check
from ops_core.store import Store
from ops_core.analysis import format_summary, format_trend, format_correlation


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


class SummaryInput(TypedDict, total=False):
    host: str
    check: str
    hours: int


class TrendInput(TypedDict):
    host: str
    check: str
    metric: str
    days: int


class CorrelateInput(TypedDict, total=False):
    run_id: str


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
    by_addr = {h.address: h for h in hosts}

    def _resolve(ident: str) -> Host | None:
        """Look up a host by alias first, then by address (IP)."""
        return by_alias.get(ident) or by_addr.get(ident)

    @tool("list_hosts", "List managed hosts, optionally filtered by tag/alias",
          ListHostsInput)
    async def list_hosts(args):
        tag = args.get("tag")
        alias = args.get("alias")
        matched = filter_hosts(hosts, tag=tag, alias=alias)
        body = "\n".join(f"{h.alias} (alias)  {h.address}  user={h.user}  tags={h.tags}" for h in matched) \
            or "(no hosts)"
        return _text(body)

    @tool("run_remote", "Run a shell command on remote hosts over SSH "
          "(read-only commands auto-run; others require approval). "
          "Use host ALIAS (not IP) from list_hosts output.",
          RunRemoteInput)
    async def run_remote(args):
        command = args["command"]
        targets = [h for ident in args["hosts"]
                   if (h := _resolve(ident)) is not None]
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

    @tool("run_inspection", "Run read-only inspection checks on hosts. "
          "Use host ALIAS (not IP) from list_hosts output.",
          RunInspectionInput)
    async def run_inspection(args):
        checks = [BUILTIN_CHECKS[c] for c in args["checks"] if c in BUILTIN_CHECKS]
        targets = [h for ident in args["hosts"]
                   if (h := _resolve(ident)) is not None]
        run_id = str(uuid.uuid4())
        rows = []
        for h in targets:
            for chk in checks:
                cr = await run_check(h, chk, executor)
                store.insert_inspection(
                    run_id=run_id, host=cr.host, check_name=cr.check_name,
                    status=cr.status, value=cr.value, raw_stdout=cr.raw,
                )
                rows.append({"host": cr.host, "check": cr.check_name,
                             "status": cr.status.value, "value": cr.value})
        return _text(json.dumps(rows, ensure_ascii=False, indent=2))

    @tool("get_inspection_history", "Get recent inspection results for a host. "
          "Use host ALIAS (not IP).",
          HistoryInput)
    async def get_inspection_history(args):
        h = _resolve(args["host"])
        host_key = h.alias if h else args["host"]
        rows = store.query_inspection(host=host_key,
                                      check_name=args.get("check"))
        if not rows:
            return _text("no inspection history for " + host_key)
        return _text(json.dumps(rows, ensure_ascii=False, indent=2,
                                default=str))

    @tool("get_inspection_summary",
          "Get aggregate inspection summary across hosts (counts by status). "
          "Available checks: disk_usage, disk_inodes, memory_usage, swap_usage, "
          "load_avg, failed_services, zombie_procs.",
          SummaryInput)
    async def get_inspection_summary(args):
        hours = int(args.get("hours", 24))
        since = (datetime.now(timezone.utc)
                 - timedelta(hours=hours)).isoformat()
        summary = store.query_summary(
            host=args.get("host"), check_name=args.get("check"),
            ts_from=since,
        )
        if summary["total"] == 0:
            return _text("No inspection data found in the last "
                         f"{hours}h. Available checks: disk_usage, "
                         "disk_inodes, memory_usage, swap_usage, load_avg, "
                         "failed_services, zombie_procs. "
                         "Run the daemon or use run_inspection to collect data.")
        return _text(format_summary(summary))

    @tool("get_inspection_trend",
          "Get time-series trend for a metric on a host/check. "
          "Valid checks: disk_usage (metric: max_pct), disk_inodes (max_inode_pct), "
          "memory_usage (pct_avail), swap_usage (pct), load_avg (ratio), "
          "failed_services (failed), zombie_procs (zombies).",
          TrendInput)
    async def get_inspection_trend(args):
        days = int(args.get("days", 7))
        trend = store.query_trend(
            host=args["host"], check_name=args["check"],
            metric_key=args["metric"], lookback_days=days,
        )
        if not trend:
            return _text(f"No trend data for {args['host']}/{args['check']}/"
                         f"{args['metric']} over {days}d. Available checks: "
                         "disk_usage, disk_inodes, memory_usage, swap_usage, "
                         "load_avg, failed_services, zombie_procs.")
        return _text(format_trend(trend, args["host"], args["check"],
                                  args["metric"]))

    @tool("get_correlated_history",
          "Get inspection results grouped by run for cross-check correlation",
          CorrelateInput)
    async def get_correlated_history(args):
        run_id = args.get("run_id")
        if run_id:
            records = store.query_inspection(run_id=run_id, limit=500)
        else:
            records = store.query_inspection(limit=100)
        return _text(format_correlation(records))

    @tool("get_host_facts", "Get facts for a host by alias (or IP as fallback)",
          FactsInput)
    async def get_host_facts(args):
        h = _resolve(args["host"])
        if h is None:
            return _text(f"unknown host: {args['host']} (use the alias from list_hosts)", is_error=True)
        return _text(json.dumps(
            {"alias": h.alias, "address": h.address, "port": h.port,
             "user": h.user, "tags": h.tags},
            ensure_ascii=False, indent=2))

    return [list_hosts, run_remote, run_inspection, get_inspection_history,
            get_host_facts, get_inspection_summary, get_inspection_trend,
            get_correlated_history]


def build_server(*, hosts: list[Host], executor: Executor, store: Store,
                 name: str = "ops") -> McpSdkServerConfig:
    tools = build_ops_tools(hosts=hosts, executor=executor, store=store)
    return create_sdk_mcp_server(name=name, tools=tools)
