from ops_core.models import (
    Host, ExecResult, CheckResult, Status, Decision, Verdict,
)


def test_host_defaults():
    h = Host(alias="web-1", address="10.0.0.11")
    assert h.port == 22
    assert h.user == "ops"
    assert h.tags == []
    assert h.bastion is None


def test_exec_result_fields():
    r = ExecResult(host="web-1", command="uptime", stdout="up", stderr="", rc=0)
    assert r.rc == 0
    assert r.timed_out is False


def test_check_result():
    c = CheckResult(host="web-1", check_name="disk_usage",
                    status=Status.WARN, value={"max_pct": 88.0})
    assert c.status == Status.WARN
    assert c.value["max_pct"] == 88.0


def test_verdict_helpers():
    assert Verdict(Decision.AUTO_ALLOW).is_auto_allow is True
    assert Verdict(Decision.DENY, "nope").is_deny is True
    assert Verdict(Decision.REQUIRE_APPROVAL).requires_approval is True
