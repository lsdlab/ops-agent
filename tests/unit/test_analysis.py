from ops_core.analysis import format_summary, format_trend, format_correlation


def test_format_summary_empty():
    out = format_summary({"total": 0, "ok": 0, "warn": 0, "crit": 0})
    assert "No inspection results" in out


def test_format_summary_normal():
    out = format_summary({"total": 10, "ok": 7, "warn": 2, "crit": 1})
    assert "Total inspections: 10" in out
    assert "OK:   7" in out
    assert "WARN: 2" in out
    assert "CRIT: 1" in out


def test_format_trend_empty():
    out = format_trend([], "web-1", "disk_usage", "max_pct")
    assert "No trend data" in out


def test_format_trend_with_data():
    trend = [
        {"ts": "2026-06-22T08:00:00.123+00:00", "value": 45.0},
        {"ts": "2026-06-23T08:00:00.456+00:00", "value": 50.0},
        {"ts": "2026-06-24T08:00:00.789+00:00", "value": 62.0},
    ]
    out = format_trend(trend, "web-1", "disk_usage", "max_pct")
    assert "web-1 / disk_usage / max_pct" in out
    assert "45.0" in out
    assert "62.0" in out
    assert "+5.00" in out
    assert "+12.00" in out


def test_format_trend_single_point():
    trend = [{"ts": "2026-06-22T08:00:00", "value": 45.0}]
    out = format_trend(trend, "web-1", "disk_usage", "max_pct")
    assert "45.0" in out
    assert "-" in out  # delta is dash for single point


def test_format_correlation_empty():
    out = format_correlation([])
    assert "No inspection records" in out


def test_format_correlation_groups():
    records = [
        {"run_id": "r1", "ts": "2026-06-22T08:00:00", "host": "web-1",
         "check_name": "disk_usage", "status": "warn", "value": {"max_pct": 88}},
        {"run_id": "r1", "ts": "2026-06-22T08:00:01", "host": "web-1",
         "check_name": "memory_usage", "status": "ok", "value": {"pct": 40}},
        {"run_id": "r2", "ts": "2026-06-23T08:00:00", "host": "db-1",
         "check_name": "disk_usage", "status": "crit", "value": {"max_pct": 95}},
    ]
    out = format_correlation(records)
    assert "run r1" in out
    assert "run r2" in out
    assert "web-1" in out
    assert "db-1" in out
    assert "disk_usage=warn" in out
    assert "memory_usage=ok" in out
    assert "disk_usage=crit" in out
