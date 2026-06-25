from __future__ import annotations
import asyncio
from typing import Protocol
from ops_core.models import Host, ExecResult


class Executor(Protocol):
    async def run(self, host: Host, command: str, timeout: float = 30.0) -> ExecResult:
        ...

    async def close(self) -> None:
        ...


class FakeExecutor:
    """In-memory executor for tests. Keys on (alias, command)."""

    def __init__(self):
        self._canned: dict[tuple[str, str], ExecResult] = {}

    def set(self, alias: str, command: str, result: ExecResult) -> None:
        self._canned[(alias, command)] = result

    async def run(self, host: Host, command: str, timeout: float = 30.0) -> ExecResult:
        return self._canned[(host.alias, command)]

    async def close(self) -> None:
        pass


class AsyncsshExecutor:
    """Real SSH executor using asyncssh."""

    def __init__(self, connect_timeout: int = 8):
        self.connect_timeout = connect_timeout

    async def run(self, host: Host, command: str, timeout: float = 30.0) -> ExecResult:
        import asyncssh

        connect_kwargs: dict = {
            "host": host.address,
            "port": host.port,
            "username": host.user,
            "known_hosts": None,
            "login_timeout": self.connect_timeout,
        }
        if host.ssh_key:
            connect_kwargs["client_keys"] = [host.ssh_key]
        try:
            async with asyncssh.connect(**connect_kwargs) as conn:
                result = await conn.run(command, timeout=timeout, check=False)
            return ExecResult(
                host=host.alias, command=command,
                stdout=result.stdout or "", stderr=result.stderr or "",
                rc=int(result.exit_status),
            )
        except Exception as exc:  # noqa: BLE001
            return ExecResult(
                host=host.alias, command=command, stdout="", stderr=f"error: {exc}",
                rc=-1,
            )

    async def close(self) -> None:
        pass


async def fan_out(executor: Executor, hosts: list[Host], command: str,
                  concurrency: int = 16, timeout: float = 30.0) -> list[ExecResult]:
    sem = asyncio.Semaphore(concurrency)

    async def one(host: Host) -> ExecResult:
        async with sem:
            try:
                return await executor.run(host, command, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                return ExecResult(
                    host=host.alias, command=command, stdout="",
                    stderr=f"error: {exc}", rc=-1,
                )

    return await asyncio.gather(*(one(h) for h in hosts))
