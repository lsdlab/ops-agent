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
class Config:
    inventory: str = "./hosts.yaml"
    sqlite_path: str = "./data/ops.db"
    concurrency: int = 16
    ssh: SshConfig = field(default_factory=SshConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    schedule: list[dict] = field(default_factory=list)


def load_config(path: str | Path) -> Config:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    ssh = SshConfig(**(raw.get("ssh") or {}))
    alerts_raw = dict(raw.get("alerts") or {})
    # YAML 1.1 (PyYAML) coerces the bare mapping key `on:` to boolean True.
    # Remap it back so AlertsConfig(**alerts_raw) gets a string keyword.
    if True in alerts_raw and "on" not in alerts_raw:
        alerts_raw["on"] = alerts_raw.pop(True)
    alerts = AlertsConfig(**alerts_raw)
    return Config(
        inventory=raw.get("inventory", "./hosts.yaml"),
        sqlite_path=raw.get("sqlite_path", "./data/ops.db"),
        concurrency=int(raw.get("concurrency", 16)),
        ssh=ssh,
        alerts=alerts,
        schedule=raw.get("schedule") or [],
    )
