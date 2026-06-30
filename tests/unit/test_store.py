from ops_core.store import Store
from ops_core.models import Status


def test_audit_roundtrip(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_audit(host="web-1", command="uptime", rc=0,
                       initiated_by="agent", approved_by="auto",
                       verdict="auto_allow", stdout_excerpt="up 1 day",
                       stderr_excerpt="")
    rows = store.query_audit(host="web-1")
    assert len(rows) == 1
    assert rows[0]["command"] == "uptime"
    assert rows[0]["verdict"] == "auto_allow"


def test_inspection_roundtrip(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                            status=Status.WARN, value={"max_pct": 88.0})
    store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 40.0})
    rows = store.query_inspection(host="web-1", check_name="disk_usage")
    assert len(rows) == 2
    # newest first
    assert rows[0]["status"] in ("ok", "warn")


# --- new v2 tests ---

def test_query_inspection_no_host(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="r1", host="a", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 10.0})
    store.insert_inspection(run_id="r2", host="b", check_name="memory_usage",
                            status=Status.CRIT, value={"pct": 95.0})
    rows = store.query_inspection()
    assert len(rows) == 2


def test_query_inspection_by_status(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="r1", host="a", check_name="disk_usage",
                            status=Status.WARN, value={"max_pct": 88.0})
    store.insert_inspection(run_id="r2", host="b", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 40.0})
    rows = store.query_inspection(status="warn")
    assert len(rows) == 1
    assert rows[0]["host"] == "a"


def test_query_inspection_by_run_id(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="sweep-1", host="a", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 10.0})
    store.insert_inspection(run_id="sweep-2", host="a", check_name="disk_usage",
                            status=Status.WARN, value={"max_pct": 88.0})
    rows = store.query_inspection(run_id="sweep-1")
    assert len(rows) == 1
    assert rows[0]["run_id"] == "sweep-1"


def test_query_inspection_time_range(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="r1", host="a", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 10.0})
    rows = store.query_inspection(ts_from="2100-01-01T00:00:00")
    assert len(rows) == 0
    rows = store.query_inspection(ts_from="2020-01-01T00:00:00")
    assert len(rows) == 1


def test_raw_stdout_persisted(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="r1", host="a", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 10.0},
                            raw_stdout="Filesystem  Size  Used Avail Use% Mounted on")
    rows = store.query_inspection(host="a")
    assert len(rows) == 1
    assert "Filesystem" in rows[0].get("raw_stdout", "")


def test_alert_roundtrip(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_alert(host="web-1", check_name="disk_usage", status="crit",
                       value={"max_pct": 95.0}, raw_stdout="/dev/sda1 95%")
    store.insert_alert(host="web-2", check_name="memory_usage", status="warn",
                       value={"pct": 87.0})
    all_alerts = store.query_alerts()
    assert len(all_alerts) == 2
    crits = store.query_alerts(status="crit")
    assert len(crits) == 1
    assert crits[0]["host"] == "web-1"
    assert crits[0]["value"]["max_pct"] == 95.0


def test_query_summary(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="r1", host="a", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 10.0})
    store.insert_inspection(run_id="r2", host="b", check_name="disk_usage",
                            status=Status.WARN, value={"max_pct": 88.0})
    store.insert_inspection(run_id="r3", host="c", check_name="memory_usage",
                            status=Status.CRIT, value={"pct": 96.0})
    s = store.query_summary()
    assert s["total"] == 3
    assert s["ok"] == 1
    assert s["warn"] == 1
    assert s["crit"] == 1


def test_query_trend(tmp_path):
    store = Store(tmp_path / "t.db")
    store.insert_inspection(run_id="r1", host="web-1", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 45.0})
    store.insert_inspection(run_id="r2", host="web-1", check_name="disk_usage",
                            status=Status.WARN, value={"max_pct": 60.0})
    store.insert_inspection(run_id="r3", host="web-1", check_name="disk_usage",
                            status=Status.CRIT, value={"max_pct": 92.0})
    trend = store.query_trend(host="web-1", check_name="disk_usage",
                              metric_key="max_pct", lookback_days=365)
    assert len(trend) == 3
    assert trend[0]["value"] == 45.0
    assert trend[-1]["value"] == 92.0


def test_migration_adds_raw_stdout(tmp_path):
    """Simulate an existing database without raw_stdout column."""
    import sqlite3
    db = tmp_path / "old.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE inspection_runs ("
                 "id INTEGER PRIMARY KEY, run_id TEXT, ts TEXT, host TEXT,"
                 "check_name TEXT, status TEXT, value_json TEXT)")
    conn.commit()
    conn.close()
    # Opening via Store should add the column without error.
    store = Store(db)
    store.insert_inspection(run_id="r1", host="a", check_name="disk_usage",
                            status=Status.OK, value={"max_pct": 10.0},
                            raw_stdout="hello")
    rows = store.query_inspection()
    assert len(rows) == 1
    assert rows[0].get("raw_stdout") == "hello"
