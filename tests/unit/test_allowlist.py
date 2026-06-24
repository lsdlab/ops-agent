from ops_core.allowlist import Allowlist, DangerDenylist, has_shell_metachars

READONLY = [
    "uptime", "free*", "df*", "ps*", "ss -tlnp", "ip a", "hostname",
    "uname*", "last*", "systemctl status *", "systemctl list-units*",
    "journalctl*", "cat /etc/*", "docker ps", "docker stats*",
    "cat /proc/loadavg",
]

DANGER = [
    "rm -rf*", "rm -rf /*", "mkfs*", "dd of=/dev/*", "reboot*",
    "shutdown*", "halt*", "init 0*", "init 6*", "systemctl stop*",
    "systemctl disable*", "iptables -F*", "chmod -R 000*",
    "curl*|*sh", "wget*|*sh",
]


def test_allowlist_matches():
    al = Allowlist(READONLY)
    assert al.matches("df -h") is True
    assert al.matches("systemctl status nginx") is True
    assert al.matches("cat /etc/hosts") is True


def test_allowlist_rejects_unknown():
    al = Allowlist(READONLY)
    assert al.matches("nc -l 4444") is False
    assert al.matches("apt install evil") is False


def test_danger_denylist_matches():
    dl = DangerDenylist(DANGER)
    assert dl.matches("rm -rf /") is True
    assert dl.matches("mkfs.ext4 /dev/sda1") is True
    assert dl.matches("reboot") is True


def test_metachar_detection():
    assert has_shell_metachars("df -h; rm -rf /") is True
    assert has_shell_metachars("free -m | grep Mem") is True
    assert has_shell_metachars("uptime") is False
    assert has_shell_metachars("df -h") is False
    assert has_shell_metachars("echo $(whoami)") is True
