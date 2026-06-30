import os
from pathlib import Path
import textwrap
from ops_core.config import load_config, apply_api_env


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


def test_load_config_with_api(tmp_path: Path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(textwrap.dedent("""
        api:
          api_key: sk-ant-test123
          base_url: https://api.example.com
    """))
    cfg = load_config(cfg_file)
    assert cfg.api.api_key == "sk-ant-test123"
    assert cfg.api.base_url == "https://api.example.com"


def test_apply_api_env_sets_vars(monkeypatch):
    from ops_core.config import ApiConfig
    # Clear any pre-existing env vars for this test
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    api = ApiConfig(api_key="sk-ant-test123", base_url="https://api.example.com")
    apply_api_env(api)
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-test123"
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://api.example.com"


def test_apply_api_env_does_not_override_existing(monkeypatch):
    from ops_core.config import ApiConfig
    monkeypatch.setenv("ANTHROPIC_API_KEY", "existing-key")
    api = ApiConfig(api_key="sk-ant-new", base_url="https://new.example.com")
    apply_api_env(api)
    # Existing env var takes precedence
    assert os.environ["ANTHROPIC_API_KEY"] == "existing-key"
