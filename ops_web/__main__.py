"""ops-web entry point: load config and start the web console."""
from __future__ import annotations
import sys
import uvicorn
from ops_core.config import load_config, apply_api_env
from ops_core.inventory import load_hosts
from ops_core.remote_exec import AsyncsshExecutor
from ops_core.store import Store
from ops_web.server import build_app


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    cfg = load_config(config_path)
    apply_api_env(cfg.api)
    hosts = load_hosts(cfg.inventory)
    executor = AsyncsshExecutor(connect_timeout=cfg.ssh.connect_timeout)
    store = Store(cfg.sqlite_path, check_same_thread=False)
    app = build_app(hosts, executor, store)
    print("ops-web starting on http://0.0.0.0:8080", file=sys.stderr)
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")


if __name__ == "__main__":
    main()
