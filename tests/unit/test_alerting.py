import asyncio
from unittest.mock import AsyncMock, patch
from ops_core.alerting import AlertSink
from ops_core.models import CheckResult, Status


def _cr(status, value):
    return CheckResult(host="web-1", check_name="disk_usage",
                       status=status, value=value)


def test_no_webhook_logs_only(capfd):
    sink = AlertSink(webhook=None, severities={"warn", "crit"})
    asyncio.run(sink.send(_cr(Status.WARN, {"max_pct": 88.0})))
    out = capfd.readouterr().out
    assert "disk_usage" in out and "web-1" in out


def test_webhook_posted_on_severity():
    sink = AlertSink(webhook="https://example.com/hook", severities={"warn", "crit"})
    mock_post = AsyncMock()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            await mock_post(url, json=json)

    with patch("ops_core.alerting.httpx.AsyncClient", return_value=FakeClient()):
        asyncio.run(sink.send(_cr(Status.CRIT, {"max_pct": 95.0})))
    assert mock_post.await_count == 1
    args, kwargs = mock_post.await_args
    assert args[0] == "https://example.com/hook"
    assert "disk_usage" in kwargs["json"]["text"]["content"]


def test_severity_filtered():
    sink = AlertSink(webhook="https://example.com/hook", severities={"crit"})
    mock_post = AsyncMock()

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            await mock_post(url, json=json)

    with patch("ops_core.alerting.httpx.AsyncClient", return_value=FakeClient()):
        asyncio.run(sink.send(_cr(Status.OK, {"max_pct": 40.0})))
    assert mock_post.await_count == 0  # ok not in severities
