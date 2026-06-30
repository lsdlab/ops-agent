"""Integration tests for the web console routes."""
from starlette.testclient import TestClient
from ops_core.models import Host, Status
from ops_core.remote_exec import FakeExecutor
from ops_core.store import Store
from ops_web.server import build_app


def _app(tmp_path, with_data=True):
    hosts = [Host(alias="web-1", address="10.0.0.11", tags=["web", "prod"]),
             Host(alias="db-1", address="10.0.0.21", tags=["db", "prod"])]
    ex = FakeExecutor()
    store = Store(tmp_path / "t.db", check_same_thread=False)
    if with_data:
        store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                                status=Status.WARN, value={"max_pct": 88.0},
                                raw_stdout="/dev/sda1 88%")
        store.insert_inspection(run_id="r1", host="web-1", check_name="memory_usage",
                                status=Status.OK, value={"pct": 42.0})
        store.insert_inspection(run_id="r2", host="db-1", check_name="disk_usage",
                                status=Status.CRIT, value={"max_pct": 95.0},
                                raw_stdout="/dev/sda1 95%")
        store.insert_alert(host="web-1", check_name="disk_usage", status="warn",
                           value={"max_pct": 88.0})
        store.insert_alert(host="db-1", check_name="disk_usage", status="crit",
                           value={"max_pct": 95.0})
    app = build_app(hosts, ex, store)
    return app


# --- Page routes ---

def test_dashboard_page(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/")
    assert r.status_code == 200
    assert "Dashboard" in r.text


def test_hosts_page(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/hosts")
    assert r.status_code == 200
    assert "web-1" in r.text
    assert "db-1" in r.text


def test_host_detail_page(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/hosts/web-1")
    assert r.status_code == 200
    assert "web-1" in r.text
    assert "disk_usage" in r.text


def test_inspections_page(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/inspections")
    assert r.status_code == 200
    assert "web-1" in r.text


def test_chat_page(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/chat")
    assert r.status_code == 200
    assert "Chat" in r.text


# --- API routes ---

def test_api_dashboard(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/api/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert data["summary"]["total"] == 3
    assert data["summary"]["warn"] == 1
    assert data["summary"]["crit"] == 1
    assert len(data["alerts"]) == 2


def test_api_hosts(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/api/hosts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["alias"] in ("web-1", "db-1")


def test_api_host_detail(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/api/hosts/web-1")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2  # disk_usage + memory_usage


def test_api_inspections_filtered(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/api/inspections?status=crit")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["host"] == "db-1"


def test_api_inspections_all(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/api/inspections")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 3


def test_api_alerts(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/api/alerts")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2


def test_api_trends(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.get("/api/trends?host=web-1&check=disk_usage&metric=max_pct&days=365")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1  # only one disk_usage record for web-1
    assert data[0]["value"] == 88.0


def test_api_chat_approve_nonexistent(tmp_path):
    client = TestClient(_app(tmp_path))
    r = client.post("/api/chat/nonexistent/approve",
                    json={"approved": True})
    assert r.status_code == 404


def test_empty_state(tmp_path):
    """Dashboard should handle no data gracefully."""
    client = TestClient(_app(tmp_path, with_data=False))
    r = client.get("/")
    assert r.status_code == 200
    # Should still render without error
    assert "Dashboard" in r.text
    r2 = client.get("/api/dashboard")
    assert r2.status_code == 200
    assert r2.json()["summary"]["total"] == 0
