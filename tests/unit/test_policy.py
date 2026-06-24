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
