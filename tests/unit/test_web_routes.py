"""Tests for ops_web/server.py routes and helpers."""
import asyncio
import json
from ops_web.server import (
    build_app, metric_for_check,
)
from ops_core.models import Host, Status
from ops_core.store import Store
from ops_core.remote_exec import FakeExecutor
import pathlib


def _store(tmp_path):
    return Store(tmp_path / "test.db", check_same_thread=False)


def _hosts():
    return [Host(alias="web-1", address="10.0.0.1", tags=["web"]),
            Host(alias="db-1", address="10.0.0.2", tags=["db"])]


def _executor():
    return FakeExecutor()


# ---- metric_for_check ----

def test_metric_for_check_disk():
    assert metric_for_check("disk_usage") == "max_pct"


def test_metric_for_check_memory():
    assert metric_for_check("memory_usage") == "pct_avail"


def test_metric_for_check_load():
    assert metric_for_check("load_avg") == "ratio"


def test_metric_for_check_failed():
    assert metric_for_check("failed_services") == "failed"


def test_metric_for_check_zombie():
    assert metric_for_check("zombie_procs") == "zombies"


def test_metric_for_check_unknown():
    assert metric_for_check("nonexistent") == "value"


# ---- App construction ----

def test_app_construction(tmp_path):
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    assert app is not None
    route_names = [r.path for r in app.routes]
    assert "/" in route_names
    assert "/hosts" in route_names
    assert "/api/dashboard" in route_names
    assert "/api/chat" in route_names
    store.close()


# ---- Page routes (using TestClient) ----

def test_dashboard_page(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    store.close()


def test_hosts_page(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/hosts")
    assert resp.status_code == 200
    assert "web-1" in resp.text
    store.close()


def test_host_detail_page(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/hosts/web-1")
    assert resp.status_code == 200
    assert "web-1" in resp.text
    store.close()


def test_inspections_page(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/inspections")
    assert resp.status_code == 200
    store.close()


def test_chat_page(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/chat")
    assert resp.status_code == 200
    store.close()


# ---- API routes ----

def test_api_dashboard(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/dashboard")
    assert resp.status_code == 200
    data = resp.json()
    assert "summary" in data
    assert "alerts" in data
    store.close()


def test_api_hosts(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/hosts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    aliases = {d["alias"] for d in data}
    assert "web-1" in aliases
    assert "db-1" in aliases
    store.close()


def test_api_host_detail(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/hosts/web-1")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    store.close()


def test_api_inspections_filter_by_host(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    # Insert some inspection data
    store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 50.0})
    store.insert_inspection(run_id="r1", host="db-1", check_name="disk_usage",
                            status=Status.WARN, value={"max_pct": 88.0})
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/inspections?host=db-1")
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["host"] == "db-1" for r in data)
    store.close()


def test_api_inspections_filter_by_status(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                            status=Status.CRIT, value={"max_pct": 95.0})
    store.insert_inspection(run_id="r1", host="db-1", check_name="memory_usage",
                            status=Status.OK, value={"pct_avail": 50.0})
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/inspections?status=crit")
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["status"] == "crit" for r in data)
    store.close()


def test_api_inspections_detail_not_found(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/inspections/99999")
    assert resp.status_code == 404
    store.close()


def test_api_alerts(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    store.insert_alert(host="web-1", check_name="disk_usage", status=Status.CRIT,
                       value={"max_pct": 95.0})
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/alerts")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    store.close()


def test_api_trends(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/trends?host=web-1&check=disk_usage&metric=max_pct")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    store.close()


def test_api_chat_approve(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    # Session doesn't exist yet, should return 404
    resp = client.post("/api/chat/nonexistent/approve",
                       json={"approved": True})
    assert resp.status_code == 404
    store.close()


# ---- New API endpoints ----

def test_api_health(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["hosts"] == 2


def test_api_config(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
    assert "checks" in data
    assert isinstance(data["checks"], list)


def test_api_host_stats(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 50.0})
    store.insert_alert(host="web-1", check_name="disk_usage", status="warn",
                       value={"max_pct": 88.0})
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/hosts/web-1/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert data["alias"] == "web-1"
    assert "summary" in data
    assert "recent_alerts" in data


def test_api_host_audit(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    store.insert_audit(host="web-1", command="df -h", rc=0,
                       initiated_by="agent", approved_by="auto", verdict="auto_allow",
                       stdout_excerpt="", stderr_excerpt="")
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/hosts/web-1/audit")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["command"] == "df -h"


def test_api_host_trends(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/api/hosts/web-1/trends")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)


def test_dashboard_includes_checks(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert "disk_usage" in resp.text


def test_audit_page_exists(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/audit")
    assert resp.status_code == 200
    assert "Audit Log" in resp.text


def test_config_page_exists(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/config")
    assert resp.status_code == 200
    assert "Configuration" in resp.text


def test_hosts_page_has_search_filter(tmp_path):
    from starlette.testclient import TestClient
    store = _store(tmp_path)
    app = build_app(hosts=_hosts(), executor=_executor(), store=store)
    client = TestClient(app)
    resp = client.get("/hosts")
    assert resp.status_code == 200
    assert "host-search" in resp.text
    assert "applyHostFilters" in resp.text


def test_metric_for_check_swap():
    assert metric_for_check("swap_usage") == "pct"


def test_metric_for_check_disk_inodes():
    assert metric_for_check("disk_inodes") == "max_inode_pct"
