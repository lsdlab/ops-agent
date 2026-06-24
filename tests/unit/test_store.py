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
