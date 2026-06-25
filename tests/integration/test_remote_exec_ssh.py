import os
import asyncio
import pytest
from ops_core.models import Host
from ops_core.remote_exec import AsyncsshExecutor

# Requires a docker container exposing sshd on 2222 with key auth for user "ops".
# Skipped unless OPS_SSH_INT_TEST=1.
pytestmark = pytest.mark.skipif(
    os.environ.get("OPS_SSH_INT_TEST") != "1",
    reason="set OPS_SSH_INT_TEST=1 and provide a docker sshd target to run",
)


def test_real_ssh_exec():
    host = Host(
        alias="sut", address="127.0.0.1", port=2222, user="ops",
        ssh_key=os.environ["OPS_SSH_KEY"],
    )
    ex = AsyncsshExecutor()
    result = asyncio.run(ex.run(host, "echo hello", timeout=10))
    asyncio.run(ex.close())
    assert result.rc == 0
    assert "hello" in result.stdout
