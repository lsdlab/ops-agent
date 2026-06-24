from pathlib import Path
import textwrap
from ops_core.config import load_config


def test_load_config(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(textwrap.dedent("""
        inventory: ./hosts.yaml
        sqlite_path: ./data/ops.db
        concurrency: 8
        ssh:
          connect_timeout: 5
          exec_timeout: 20
        alerts:
          webhook: https://example.com/hook
          on: [warn, crit]
    """))
    cfg = load_config(cfg_file)
    assert cfg.concurrency == 8
    assert cfg.sqlite_path == "./data/ops.db"
    assert cfg.ssh.exec_timeout == 20
    assert cfg.alerts.webhook == "https://example.com/hook"
    assert "crit" in cfg.alerts.on
