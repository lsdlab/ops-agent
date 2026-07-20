"""Tests for ops_client/approval.py — cache and tool-name matching."""
import time
from ops_client.approval import _ApprovalCache, _is_run_remote


# ---- _is_run_remote ----

def test_is_run_remote_exact():
    assert _is_run_remote("run_remote") is True


def test_is_run_remote_sdk_suffix():
    assert _is_run_remote("run_remote__run_remote") is True


def test_is_run_remote_other():
    assert _is_run_remote("list_hosts") is False
    assert _is_run_remote("run_inspection") is False
    assert _is_run_remote("run") is False


# ---- _ApprovalCache ----

def test_cache_miss():
    cache = _ApprovalCache()
    assert cache.check("df -h") is None


def test_cache_record_and_hit():
    cache = _ApprovalCache()
    cache.record("df -h", True)
    assert cache.check("df -h") is True


def test_cache_deny_not_cached():
    cache = _ApprovalCache()
    cache.record("df -h", False)
    assert cache.check("df -h") is None  # denials are not cached


def test_cache_expiry():
    cache = _ApprovalCache(ttl=0)  # TTL=0 means immediately expired
    cache.record("df -h", True)
    assert cache.check("df -h") is None  # expired


def test_cache_expiry_partial():
    cache = _ApprovalCache(ttl=0.1)  # 100ms
    cache.record("cmd1", True)
    time.sleep(0.15)
    cache.record("cmd2", True)
    # cmd1 should be expired, cmd2 should be active
    assert cache.check("cmd1") is None
    assert cache.check("cmd2") is True


def test_cache_bounded():
    cache = _ApprovalCache(ttl=3600)
    for i in range(30):
        cache.record(f"cmd{i}", True)
    assert len(cache._cache) <= 20


def test_cache_multiple_entries():
    cache = _ApprovalCache()
    cache.record("cmd1", True)
    cache.record("cmd2", True)
    assert cache.check("cmd1") is True
    assert cache.check("cmd2") is True
    assert cache.check("cmd3") is None
