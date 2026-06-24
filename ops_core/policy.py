from __future__ import annotations
from ops_core.allowlist import Allowlist, DangerDenylist, has_shell_metachars
from ops_core.models import Decision, Verdict


class Policy:
    """Decides whether a command auto-runs, needs approval, or is denied.

    Precedence: danger deny (hard stop) > shell metachar (smuggling risk)
    > read-only allowlist (auto) > everything else (needs approval).
    """

    def __init__(self, allowlist: Allowlist, denylist: DangerDenylist):
        self.allowlist = allowlist
        self.denylist = denylist

    def decide(self, command: str, context: str = "interactive") -> Verdict:
        if self.denylist.matches(command):
            return Verdict(Decision.DENY, "command matches the danger denylist")
        if has_shell_metachars(command):
            return Verdict(Decision.REQUIRE_APPROVAL,
                           "command contains shell metacharacters")
        if self.allowlist.matches(command):
            return Verdict(Decision.AUTO_ALLOW)
        return Verdict(Decision.REQUIRE_APPROVAL, "command not on read-only allowlist")


def decide(command: str, allowlist: Allowlist, denylist: DangerDenylist,
           context: str = "interactive") -> Verdict:
    return Policy(allowlist, denylist).decide(command, context)
