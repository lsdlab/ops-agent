"""Tests for ops_daemon/__main__.py — dedup, formatting, target resolution."""
from ops_daemon.__main__ import (
    _should_alert, _emoji, _colour, _fmt_value, _resolve_targets,
    validate_checks,
)
from ops_core.models import Host, Status
from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.inspection import BUILTIN_CHECKS


# ---- _should_alert ----

def test_should_alert_first_time():
    import ops_daemon.__main__ as daemon
    daemon._alert_state.clear()
    assert _should_alert("web-1", "disk_usage", "crit") is True


def test_should_alert_on_change():
    import ops_daemon.__main__ as daemon
    daemon._alert_state.clear()
    daemon._alert_state["web-1:disk_usage"] = "ok"
    assert _should_alert("web-1", "disk_usage", "crit") is True


def test_should_alert_no_change():
    import ops_daemon.__main__ as daemon
    daemon._alert_state.clear()
    daemon._alert_state["web-1:disk_usage"] = "crit"
    assert _should_alert("web-1", "disk_usage", "crit") is False


def test_should_alert_crit_to_ok():
    import ops_daemon.__main__ as daemon
    daemon._alert_state.clear()
    daemon._alert_state["web-1:disk_usage"] = "crit"
    assert _should_alert("web-1", "disk_usage", "ok") is True


def test_should_alert_different_check():
    import ops_daemon.__main__ as daemon
    daemon._alert_state.clear()
    daemon._alert_state["web-1:disk_usage"] = "crit"
    assert _should_alert("web-1", "memory_usage", "warn") is True


def test_should_alert_different_host():
    import ops_daemon.__main__ as daemon
    daemon._alert_state.clear()
    daemon._alert_state["web-1:disk_usage"] = "crit"
    assert _should_alert("web-2", "disk_usage", "crit") is True


# ---- _emoji ----

def test_emoji_ok():
    assert _emoji("ok") == "✓"


def test_emoji_warn():
    assert _emoji("warn") == "△"


def test_emoji_crit():
    assert _emoji("crit") == "✕"


def test_emoji_unknown():
    assert _emoji("unknown") == "?"


# ---- _colour ----

def test_colour_crit():
    assert _colour("crit") == "\033[31m"


def test_colour_warn():
    assert _colour("warn") == "\033[33m"


def test_colour_ok():
    assert _colour("ok") == "\033[32m"


def test_colour_unknown():
    assert _colour("unknown") == ""


# ---- _fmt_value ----

def test_fmt_value_float():
    assert _fmt_value({"max_pct": 85.5}) == "max_pct=85.5"


def test_fmt_value_int():
    assert _fmt_value({"failed": 2}) == "failed=2"


def test_fmt_value_empty():
    assert _fmt_value({}) == ""


def test_fmt_value_none():
    assert _fmt_value(None) == ""


def test_fmt_value_mixed():
    result = _fmt_value({"max_pct": 90.0, "failed": 1})
    assert "max_pct=90.0" in result
    assert "failed=1" in result


# ---- _resolve_targets ----

def test_resolve_all_hosts():
    hosts = [Host(alias="web-1", address="10.0.0.1", tags=["web"]),
             Host(alias="db-1", address="10.0.0.2", tags=["db"])]
    result = _resolve_targets(hosts, {})
    assert len(result) == 2


def test_resolve_by_tag():
    hosts = [Host(alias="web-1", address="10.0.0.1", tags=["web", "prod"]),
             Host(alias="db-1", address="10.0.0.2", tags=["db", "prod"])]
    result = _resolve_targets(hosts, {"hosts": "tag:web"})
    assert len(result) == 1
    assert result[0].alias == "web-1"


def test_resolve_by_alias_list():
    hosts = [Host(alias="web-1", address="10.0.0.1", tags=["web"]),
             Host(alias="db-1", address="10.0.0.2", tags=["db"])]
    result = _resolve_targets(hosts, {"hosts": ["web-1"]})
    assert len(result) == 1
    assert result[0].alias == "web-1"


# ---- validate_checks ----

def test_validate_ok():
    checks = list(BUILTIN_CHECKS.values())
    problems = validate_checks(checks)
    assert problems == []  # every built-in must pass allowlist validation


def test_validate_denylist_match():
    from ops_core.models import Check
    bad_check = Check(name="bad", command="rm -rf /",
                      parse=lambda x: {}, evaluate=lambda x: Status.OK)
    problems = validate_checks([bad_check])
    assert any("denylist" in p for p in problems)


def test_validate_allowlist_miss():
    from ops_core.models import Check
    bad_check = Check(name="custom", command="curl http://evil.com",
                      parse=lambda x: {}, evaluate=lambda x: Status.OK)
    problems = validate_checks([bad_check])
    assert any("allowlist" in p for p in problems)


def test_validate_accepts_load_avg_metachar():
    # load_avg legitimately uses `;` to combine two reads. The daemon's
    # allowlist must accept this exact built-in command (it does NOT apply
    # the metachar downgrade the interactive client does).
    problems = validate_checks([BUILTIN_CHECKS["load_avg"]])
    assert problems == []


def test_validate_rejects_smuggled_loadavg():
    # A `;`-smuggled command must NOT ride the load_avg allowlist pattern.
    # Regression guard for the greedy-fnmatch hole (was `cat /proc/loadavg*`).
    from ops_core.models import Check
    smuggled = Check(name="evil", command="cat /proc/loadavg; rm -rf /tmp/x",
                     parse=lambda x: {}, evaluate=lambda x: Status.OK)
    problems = validate_checks([smuggled])
    assert any("allowlist" in p for p in problems)
