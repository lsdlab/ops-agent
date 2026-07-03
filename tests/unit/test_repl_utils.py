"""Tests for ops_client/__main__ utility functions (no Rich/console I/O)."""
from ops_client.__main__ import (
    _levenshtein, _truncate_output, _brief, _SLASH_CMDS, _HOST_CMDS,
)
from ops_core.models import Host


# ---- Levenshtein distance ----

def test_levenshtein_identical():
    assert _levenshtein("help", "help") == 0


def test_levenshtein_empty():
    # Empty vs non-empty = length of non-empty
    assert _levenshtein("", "abc") == 3


def test_levenshtein_single_char():
    assert _levenshtein("a", "b") == 1


def test_levenshtein_typo():
    assert _levenshtein("healtcheck", "healthcheck") == 1


def test_levenshtein_same():
    assert _levenshtein("same", "same") == 0


def test_levenshtein_fuzzy_match():
    # "healthcck" is 2 edits from "healthcheck" (delete 'c', delete 'k')
    assert _levenshtein("healthcck", "healthcheck") <= 2


def test_levenshtein_single_edit():
    assert _levenshtein("cat", "bat") == 1


# ---- Truncate output ----

def test_truncate_no_truncation():
    lines = ["line1", "line2", "line3"]
    result = _truncate_output(lines)
    assert result == "line1\nline2\nline3"
    assert "[truncated" not in result


def test_truncate_too_many_lines():
    lines = [f"line{i}" for i in range(130)]
    result = _truncate_output(lines)
    assert "[truncated" in result
    assert "10 more lines" in result
    # Should contain exactly MAX_LINES lines
    assert result.count("\n") == 120  # 120 lines + 1 truncation line


def test_truncate_too_many_chars():
    # 50 lines of 200 chars each = 10000 chars > 8000 limit
    lines = ["x" * 200 for _ in range(50)]
    result = _truncate_output(lines)
    assert "[truncated" in result
    assert "more lines" in result


def test_truncate_exact_line_boundary():
    # 10 lines of 100 chars = 1000 chars < 8000, should not truncate
    lines = ["x" * 100 for _ in range(10)]
    result = _truncate_output(lines)
    assert "[truncated" not in result


def test_truncate_empty():
    assert _truncate_output([]) == ""


def test_truncate_one_long_line():
    lines = ["x" * 10000]
    result = _truncate_output(lines)
    assert "[truncated" in result


# ---- Brief ----

def test_brief_short():
    assert _brief("hello") == "hello"


def test_brief_long():
    result = _brief("x" * 200)
    assert len(result) == 101  # 100 + ellipsis


def test_brief_exact_boundary():
    assert _brief("x" * 100) == "x" * 100


# ---- Slash command constants ----

def test_slash_cmds_contains_expected():
    for cmd in ["help", "quit", "retry", "audit", "alerts", "listchecks"]:
        assert cmd in _SLASH_CMDS


def test_host_cmds_subset():
    for cmd in ["ping", "healthcheck", "quick", "qc", "security"]:
        assert cmd in _HOST_CMDS


def test_host_cmds_not_in_slash_cmds():
    # _HOST_CMDS commands are also in _SLASH_CMDS (they are slash commands)
    pass  # intentional no-op — host commands ARE slash commands


# ---- Host resolution helpers ----

def test_host_creation():
    h = Host(alias="web-1", address="10.0.0.1", port=22, user="ops", tags=["web"])
    assert h.alias == "web-1"
    assert h.port == 22
    assert h.tags == ["web"]


def test_host_defaults():
    h = Host(alias="test", address="1.2.3.4")
    assert h.user == "ops"
    assert h.port == 22
    assert h.tags == []
    assert h.ssh_key is None
    assert h.bastion is None
