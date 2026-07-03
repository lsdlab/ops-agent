from __future__ import annotations
import asyncio
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
from ops_core.store import Store, _excerpt
from ops_core.analysis import format_summary, format_trend, format_correlation


class ListHostsInput(TypedDict, total=False):
    tag: str
    alias: str


class RunRemoteInput(TypedDict):
    hosts: list[str]
    command: str


class RunInspectionInput(TypedDict):
    hosts: list[str]
    checks: list[str]


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


class ListChecksInput(TypedDict, total=False):
    pass


class AuditQueryInput(TypedDict, total=False):
    host: str
    limit: int


class AlertQueryInput(TypedDict, total=False):
    host: str
    status: str
    limit: int


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
        command = args.get("command")
        if not command:
            return _text("missing required field: command", is_error=True)
        targets_ident = args.get("hosts")
        if not targets_ident:
            return _text("missing required field: hosts", is_error=True)
        # Resolve hosts, report unknown ones
        targets = []
        unknown = []
        for ident in targets_ident:
            if (h := _resolve(ident)) is not None:
                targets.append(h)
            else:
                unknown.append(ident)
        if unknown:
            return _text(
                f"unknown host(s): {', '.join(unknown)} "
                f"(use the alias from list_hosts). "
                f"Available: {', '.join(h.alias for h in hosts)}",
                is_error=True,
            )
        verdict = policy.decide(command, "interactive")
        if verdict.is_deny:
            return _text(
                f"command denied by policy: {verdict.reason}",
                is_error=True,
            )
        if not targets:
            return _text("(no targets matched)", is_error=True)
        results = await fan_out(executor, targets, command)
        for r in results:
            store.insert_audit(
                host=r.host, command=command, rc=r.rc,
                initiated_by="agent",
                approved_by="auto" if verdict.is_auto_allow else "user",
                verdict=verdict.decision.value,
                stdout_excerpt=_excerpt(r.stdout),
                stderr_excerpt=_excerpt(r.stderr),
            )
        lines = [f"--- {r.host} (rc={r.rc}) ---\n{_excerpt(r.stdout)}{_excerpt(r.stderr)}"
                 for r in results]
        return _text("\n\n".join(lines) or "(no results)")

    @tool("run_inspection", "Run read-only inspection checks on hosts. "
          "Use host ALIAS (not IP) from list_hosts output.",
          RunInspectionInput)
    async def run_inspection(args):
        checks_ident = args.get("checks", [])
        if not checks_ident:
            return _text("missing required field: checks", is_error=True)
        targets_ident = args.get("hosts")
        if not targets_ident:
            return _text("missing required field: hosts", is_error=True)
        # Check names validation
        unknown_checks = [c for c in checks_ident if c not in BUILTIN_CHECKS]
        if unknown_checks:
            return _text(
                f"unknown check(s): {', '.join(unknown_checks)}. "
                f"Available: {', '.join(BUILTIN_CHECKS.keys())}",
                is_error=True,
            )
        checks = [BUILTIN_CHECKS[c] for c in checks_ident]
        # Resolve hosts, report unknown ones
        targets = []
        unknown_hosts = []
        for ident in targets_ident:
            if (h := _resolve(ident)) is not None:
                targets.append(h)
            else:
                unknown_hosts.append(ident)
        if unknown_hosts:
            return _text(
                f"unknown host(s): {', '.join(unknown_hosts)} "
                f"(use the alias from list_hosts). "
                f"Available: {', '.join(h.alias for h in hosts)}",
                is_error=True,
            )
        run_id = str(uuid.uuid4())
        # Parallel execution: all host×check combinations concurrently
        tasks = []
        for h in targets:
            for chk in checks:
                tasks.append(run_check(h, chk, executor))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        rows = []
        for cr in results:
            if isinstance(cr, Exception):
                continue
            store.insert_inspection(
                run_id=run_id, host=cr.host, check_name=cr.check_name,
                status=cr.status, value=cr.value, raw_stdout=cr.raw,
            )
            rows.append({"host": cr.host, "check": cr.check_name,
                         "status": cr.status.value, "value": cr.value})
        return _text(json.dumps(
            {"run_id": run_id, "rows": rows},
            ensure_ascii=False, indent=2,
        ))

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
          f"Available checks: {', '.join(BUILTIN_CHECKS.keys())}.",
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
            return _text(f"No inspection data found in the last {hours}h. "
                         f"Available checks: {', '.join(BUILTIN_CHECKS.keys())}. "
                         "Run the daemon or use run_inspection to collect data.")
        return _text(format_summary(summary))

    @tool("get_inspection_trend",
          "Get time-series trend for a metric on a host/check. "
          "Valid checks: disk_usage (metric: max_pct), disk_inodes (max_inode_pct), "
          "memory_usage (pct_avail), swap_usage (pct), load_avg (ratio), "
          "failed_services (failed), zombie_procs (zombies).",
          TrendInput)
    async def get_inspection_trend(args):
        host = args.get("host")
        check_name = args.get("check")
        metric_key = args.get("metric")
        if not host:
            return _text("missing required field: host", is_error=True)
        if not check_name:
            return _text("missing required field: check", is_error=True)
        if not metric_key:
            return _text("missing required field: metric", is_error=True)
        if check_name not in BUILTIN_CHECKS:
            return _text(
                f"unknown check: {check_name}. "
                f"Available: {', '.join(BUILTIN_CHECKS.keys())}",
                is_error=True,
            )
        days = int(args.get("days", 7))
        trend = store.query_trend(
            host=host, check_name=check_name,
            metric_key=metric_key, lookback_days=days,
        )
        if not trend:
            return _text(f"No trend data for {host}/{check_name}/{metric_key} "
                         f"over {days}d. Available checks: "
                         f"{', '.join(BUILTIN_CHECKS.keys())}.")
        return _text(format_trend(trend, host, check_name, metric_key))

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

    _AVAILABLE_CHECKS = ", ".join(BUILTIN_CHECKS.keys())

    @tool("list_checks", "List available inspection checks and their descriptions",
          ListChecksInput)
    async def list_checks(args):
        lines = []
        for name, chk in BUILTIN_CHECKS.items():
            lines.append(f"  {name}: {chk.command}")
        return _text("\n".join(lines))

    @tool("query_audit",
          "Query the command audit log for recent commands run by the agent. "
          "Use host ALIAS (not IP).",
          AuditQueryInput)
    async def query_audit(args):
        host = args.get("host")
        limit = int(args.get("limit", 50))
        rows = store.query_audit(host=host, limit=limit)
        if not rows:
            return _text(f"no audit records" + (f" for {host}" if host else ""))
        return _text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))

    @tool("query_alerts",
          "Query alert history for hosts with warn/crit status. "
          "Use host ALIAS (not IP).",
          AlertQueryInput)
    async def query_alerts(args):
        host = args.get("host")
        status = args.get("status")
        limit = int(args.get("limit", 50))
        rows = store.query_alerts(host=host, status=status, limit=limit)
        if not rows:
            msg = f"no alerts"
            if host:
                msg += f" for {host}"
            if status:
                msg += f" with status {status}"
            return _text(msg)
        return _text(json.dumps(rows, ensure_ascii=False, indent=2, default=str))

    return [list_hosts, run_remote, run_inspection, get_inspection_history,
            get_host_facts, get_inspection_summary, get_inspection_trend,
            get_correlated_history, list_checks, query_audit, query_alerts]


def build_server(*, hosts: list[Host], executor: Executor, store: Store,
                 name: str = "ops") -> McpSdkServerConfig:
    tools = build_ops_tools(hosts=hosts, executor=executor, store=store)
    return create_sdk_mcp_server(name=name, tools=tools)
