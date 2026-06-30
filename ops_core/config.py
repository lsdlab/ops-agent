from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class SshConfig:
    connect_timeout: int = 8
    exec_timeout: int = 30


@dataclass
class AlertsConfig:
    webhook: str | None = None
    on: list[str] = field(default_factory=lambda: ["warn", "crit"])


@dataclass
class ApiConfig:
    api_key: str | None = None
    base_url: str | None = None


@dataclass
class Config:
    inventory: str = "./hosts.yaml"
    sqlite_path: str = "./data/ops.db"
    concurrency: int = 16
    ssh: SshConfig = field(default_factory=SshConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    api: ApiConfig = field(default_factory=ApiConfig)
    schedule: list[dict] = field(default_factory=list)


def apply_api_env(api: ApiConfig) -> None:
    """Set ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL from config when provided.

    Environment variables already set take precedence; config only fills
    gaps so the user can still override via the shell.
    """
    import os
    if api.api_key and not os.environ.get("ANTHROPIC_API_KEY"):
        os.environ["ANTHROPIC_API_KEY"] = api.api_key
    if api.base_url and not os.environ.get("ANTHROPIC_BASE_URL"):
        os.environ["ANTHROPIC_BASE_URL"] = api.base_url


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    ssh = SshConfig(**(raw.get("ssh") or {}))
    alerts_raw = dict(raw.get("alerts") or {})
    # YAML 1.1 (PyYAML) coerces the bare mapping key `on:` to boolean True.
    # Remap it back so AlertsConfig(**alerts_raw) gets a string keyword.
    if True in alerts_raw and "on" not in alerts_raw:
        alerts_raw["on"] = alerts_raw.pop(True)
    alerts = AlertsConfig(**alerts_raw)
    api = ApiConfig(**(raw.get("api") or {}))
    return Config(
        inventory=raw.get("inventory", "./hosts.yaml"),
        sqlite_path=raw.get("sqlite_path", "./data/ops.db"),
        concurrency=int(raw.get("concurrency", 16)),
        ssh=ssh,
        alerts=alerts,
        api=api,
        schedule=raw.get("schedule") or [],
    )
