"""Starlette web application for the ops-agent web console."""

from __future__ import annotations
import asyncio
import json
from contextlib import asynccontextmanager
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Route
from sse_starlette.sse import EventSourceResponse
from claude_agent_sdk import ClaudeAgentOptions

from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.models import Host
from ops_core.remote_exec import Executor
from ops_core.inspection import BUILTIN_CHECKS
from ops_core.store import Store

from ops_web.templates import (
    dashboard_page, hosts_page, host_detail_page,
    inspections_page, chat_page,
)
from ops_web.chat import SessionStore, run_chat_sse


def build_app(hosts: list[Host], executor: Executor, store: Store) -> Starlette:
    allowlist = Allowlist(DEFAULT_READONLY)
    denylist = DangerDenylist(DEFAULT_DANGER)
    sessions = SessionStore()
    by_alias = {h.alias: h for h in hosts}

    # ---- Page routes ----

    async def dashboard(request: Request) -> HTMLResponse:
        summary = store.query_summary()
        alerts = store.query_alerts(limit=50)
        return HTMLResponse(dashboard_page(summary, alerts))

    async def hosts_list(request: Request) -> HTMLResponse:
        data = []
        for h in hosts:
            rows = store.query_inspection(host=h.alias, limit=5)
            worst = "ok"
            for r in rows:
                if r.get("status") == "crit":
                    worst = "crit"; break
                if r.get("status") == "warn":
                    worst = "warn"
            data.append({"alias": h.alias, "address": h.address,
                         "worst_status": worst, "tags": h.tags})
        return HTMLResponse(hosts_page(data))

    async def host_detail(request: Request) -> HTMLResponse:
        alias = request.path_params["alias"]
        insp = store.query_inspection(host=alias, limit=50)
        # Build a simple trend section for each check that has data
        checks_seen = set(r["check_name"] for r in insp)
        trend_parts = []
        for ck in checks_seen:
            trend = store.query_trend(host=alias, check_name=ck,
                                      metric_key=metric_for_check(ck),
                                      lookback_days=7)
            if len(trend) >= 2:
                values = [p["value"] for p in trend]
                delta = float(values[-1]) - float(values[0])
                trend_parts.append(
                    f'<div style="margin-bottom:0.5rem"><strong>{ck}</strong>: '
                    f'{values[0]} → {values[-1]} '
                    f'(<span class="{"crit" if delta > 0 else "ok"}">{delta:+.1f}</span> '
                    f'over 7d)</div>')
        trend_html = ("<h2>Trends (7d)</h2>" + "".join(trend_parts)) if trend_parts else ""
        return HTMLResponse(host_detail_page(alias, insp, trend_html))

    async def inspections(request: Request) -> HTMLResponse:
        host_list = sorted({h.alias for h in hosts})
        check_list = sorted(BUILTIN_CHECKS.keys())
        insp = store.query_inspection(limit=200)
        return HTMLResponse(inspections_page(host_list, check_list, insp))

    async def chat(request: Request) -> HTMLResponse:
        return HTMLResponse(chat_page())

    # ---- API routes ----

    async def api_dashboard(request: Request) -> JSONResponse:
        summary = store.query_summary()
        alerts = store.query_alerts(limit=50)
        return JSONResponse({"summary": summary, "alerts": alerts})

    async def api_hosts(request: Request) -> JSONResponse:
        data = []
        for h in hosts:
            rows = store.query_inspection(host=h.alias, limit=5)
            worst = "ok"
            for r in rows:
                if r.get("status") == "crit":
                    worst = "crit"; break
                if r.get("status") == "warn":
                    worst = "warn"
            data.append({"alias": h.alias, "address": h.address,
                         "port": h.port, "user": h.user, "tags": h.tags,
                         "worst_status": worst})
        return JSONResponse(data)

    async def api_host_detail(request: Request) -> JSONResponse:
        alias = request.path_params["alias"]
        insp = store.query_inspection(host=alias, limit=50)
        return JSONResponse(insp)

    async def api_inspections(request: Request) -> JSONResponse:
        params = request.query_params
        kwargs = {"limit": int(params.get("limit", 200))}
        if params.get("host"):
            kwargs["host"] = params["host"]
        if params.get("check"):
            kwargs["check_name"] = params["check"]
        if params.get("status"):
            kwargs["status"] = params["status"]
        insp = store.query_inspection(**kwargs)
        return JSONResponse(insp)

    async def api_inspection_detail(request: Request) -> JSONResponse:
        insp_id = request.path_params["id"]
        rows = store.query_inspection(limit=1)
        # Simple id lookup — in a real app we'd query by primary key
        for r in rows:
            if str(r.get("id")) == insp_id:
                return JSONResponse(r)
        return JSONResponse({"error": "not found"}, status_code=404)

    async def api_alerts(request: Request) -> JSONResponse:
        params = request.query_params
        alerts = store.query_alerts(
            host=params.get("host"),
            status=params.get("status"),
            limit=int(params.get("limit", 100)),
        )
        return JSONResponse(alerts)

    async def api_trends(request: Request) -> JSONResponse:
        params = request.query_params
        host = params.get("host", "")
        check = params.get("check", "")
        metric = params.get("metric", metric_for_check(check))
        days = int(params.get("days", 7))
        trend = store.query_trend(host=host, check_name=check,
                                  metric_key=metric, lookback_days=days)
        return JSONResponse(trend)

    async def api_chat(request: Request) -> StreamingResponse:
        """SSE streaming chat endpoint."""
        query_params = dict(request.query_params)
        message = query_params.get("message", "")
        session_id = query_params.get("session_id")

        async def event_stream():
            q = asyncio.Queue()

            def send_event(evt_type: str, data: str) -> None:
                q.put_nowait({"event": evt_type, "data": data})

            async def run_agent():
                try:
                    await run_chat_sse(
                        message=message, session_id=session_id,
                        options_builder=_build_agent_options(hosts, executor, store),
                        sessions=sessions,
                        allowlist=allowlist, denylist=denylist,
                        send_event=send_event,
                    )
                except Exception as exc:
                    send_event("error", str(exc))
                finally:
                    q.put_nowait(None)  # sentinel

            task = asyncio.create_task(run_agent())
            while True:
                item = await q.get()
                if item is None:
                    break
                yield item
            await task

        return EventSourceResponse(event_stream())

    async def api_chat_approve(request: Request) -> JSONResponse:
        session_id = request.path_params["session_id"]
        body = await request.json()
        approved = bool(body.get("approved", False))
        session = sessions.get(session_id)
        if session:
            session.resolve_approval(approved)
            return JSONResponse({"ok": True})
        return JSONResponse({"ok": False, "error": "session not found"},
                            status_code=404)

    # ---- Routes ----
    routes = [
        Route("/", dashboard, methods=["GET"]),
        Route("/hosts", hosts_list, methods=["GET"]),
        Route("/hosts/{alias}", host_detail, methods=["GET"]),
        Route("/inspections", inspections, methods=["GET"]),
        Route("/chat", chat, methods=["GET"]),
        # API
        Route("/api/dashboard", api_dashboard, methods=["GET"]),
        Route("/api/hosts", api_hosts, methods=["GET"]),
        Route("/api/hosts/{alias}", api_host_detail, methods=["GET"]),
        Route("/api/inspections", api_inspections, methods=["GET"]),
        Route("/api/inspections/{id}", api_inspection_detail, methods=["GET"]),
        Route("/api/alerts", api_alerts, methods=["GET"]),
        Route("/api/trends", api_trends, methods=["GET"]),
        Route("/api/chat", api_chat, methods=["GET"]),  # SSE via GET
        Route("/api/chat/{session_id}/approve", api_chat_approve, methods=["POST"]),
    ]

    @asynccontextmanager
    async def lifespan(app):
        task = asyncio.create_task(sessions.expire_loop())
        yield
        task.cancel()

    app = Starlette(routes=routes, lifespan=lifespan)
    return app


def metric_for_check(check_name: str) -> str:
    """Return the primary metric key for each built-in check."""
    metrics = {
        "disk_usage": "max_pct",
        "memory_usage": "pct",
        "load_avg": "load1",
        "failed_services": "failed",
        "zombie_procs": "zombies",
    }
    return metrics.get(check_name, "value")


def _build_agent_options(hosts, executor, store):
    """Return a factory that builds ClaudeAgentOptions with a given can_use_tool."""
    from ops_mcp.server import build_server  # noqa: F811
    from ops_client.__main__ import ALLOWED, DISALLOWED  # noqa: F811
    from ops_client.prompts import SYSTEM_PROMPT as SP  # noqa: F811

    import os as _os
    server = build_server(hosts=hosts, executor=executor, store=store)

    def build(allowlist, denylist, can_use_tool):
        env_vars = {}
        for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"):
            val = _os.environ.get(var)
            if val:
                env_vars[var] = val
        return ClaudeAgentOptions(
            mcp_servers={"ops": server},
            allowed_tools=ALLOWED,
            disallowed_tools=DISALLOWED,
            can_use_tool=can_use_tool,
            permission_mode="default",
            system_prompt=SP,
            max_turns=40,
            env=env_vars,
        )

    return build

