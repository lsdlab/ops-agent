from __future__ import annotations
import fnmatch
import re

# Characters that enable shell chaining / substitution / smuggling.
_METACHAR_RE = re.compile(r"[;&|`$(){}<>\n\\]")


def has_shell_metachars(command: str) -> bool:
    return bool(_METACHAR_RE.search(command))


def _compile(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(fnmatch.translate(p), re.DOTALL) for p in patterns]


class Allowlist:
    """Read-only command allowlist. Matches the full command string."""

    def __init__(self, patterns: list[str]):
        self._patterns = _compile(patterns)

    def matches(self, command: str) -> bool:
        cmd = command.strip()
        return any(p.match(cmd) for p in self._patterns)


class DangerDenylist:
    """Commands that are denied outright even if otherwise approved."""

    def __init__(self, patterns: list[str]):
        self._patterns = _compile(patterns)

    def matches(self, command: str) -> bool:
        cmd = command.strip()
        return any(p.match(cmd) for p in self._patterns)


# Default sets used across daemon and client.
DEFAULT_READONLY = [
    "uptime", "free*", "df*", "ps*", "ss -tlnp", "ip a", "ip addr*",
    "hostname", "uname*", "last*", "systemctl status *",
    "systemctl list-units*", "journalctl*", "cat /etc/*",
    "cat /proc/loadavg*", "cat /proc/meminfo*", "nproc*",
    "docker ps", "docker stats*",
]

DEFAULT_DANGER = [
    "rm -rf*", "mkfs*", "dd of=/dev/*", "reboot*", "shutdown*", "halt*",
    "init 0*", "init 6*", "systemctl stop*", "systemctl disable*",
    "iptables -F*", "chmod -R 000*", "curl*|*sh", "wget*|*sh",
    ":*:*&*", "> /etc/*",
]
