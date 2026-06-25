from __future__ import annotations
import sys
import httpx
from ops_core.models import CheckResult


class AlertSink:
    """Sends alerts to a webhook (if configured) and always logs to stdout."""

    def __init__(self, webhook: str | None, severities: set[str]):
        self.webhook = webhook
        self.severities = severities

    async def send(self, result: CheckResult) -> None:
        if result.status.value not in self.severities:
            return
        text = (f"[{result.status.value.upper()}] {result.host} "
                f"{result.check_name}: {result.value}")
        print(text, file=sys.stdout, flush=True)
        if self.webhook:
            payload = {"msgtype": "text",
                       "text": {"content": f"ops-agent alert: {text}"}}
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(self.webhook, json=payload)
            except Exception as exc:  # noqa: BLE001
                print(f"alert webhook failed: {exc}", file=sys.stderr, flush=True)
