from ops_core.allowlist import Allowlist, DangerDenylist, DEFAULT_READONLY, DEFAULT_DANGER
from ops_core.policy import decide, Policy
from ops_core.models import Decision

AL = Allowlist(DEFAULT_READONLY)
DL = DangerDenylist(DEFAULT_DANGER)
POL = Policy(AL, DL)


def test_auto_allow_readonly():
    v = POL.decide("df -h")
    assert v.is_auto_allow


def test_deny_dangerous():
    v = POL.decide("rm -rf /")
    assert v.is_deny


def test_metachar_downgrades_to_approval():
    # `df -h` is allowlisted, but the `;` smuggles -> require approval.
    v = POL.decide("df -h; echo hi")
    assert v.requires_approval


def test_unknown_requires_approval():
    v = POL.decide("nc -l 4444")
    assert v.requires_approval


def test_deny_beats_metachar():
    # `rm -rf /` has no metachar but is dangerous -> Deny.
    v = POL.decide("rm -rf /var")
    assert v.is_deny


def test_load_avg_command_requires_approval_in_client():
    # Daemon/client asymmetry, documented on purpose: the built-in load_avg
    # command contains `;`. The interactive client's policy sees the metachar
    # and requires approval, even though the daemon's validate_checks accepts
    # it (the daemon runs it directly, never via this policy path).
    v = POL.decide("cat /proc/loadavg; nproc")
    assert v.requires_approval


def test_allowlist_exact_loadavg_blocks_smuggling():
    # The allowlist matches the exact built-in command...
    assert AL.matches("cat /proc/loadavg; nproc") is True
    # ...but not a `;`-smuggled variant (guards the old greedy `cat /proc/loadavg*`).
    assert AL.matches("cat /proc/loadavg; rm -rf /") is False
