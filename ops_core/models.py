from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum


class Status(str, Enum):
    OK = "ok"
    WARN = "warn"
    CRIT = "crit"


class Decision(str, Enum):
    AUTO_ALLOW = "auto_allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


@dataclass
class Host:
    alias: str
    address: str
    port: int = 22
    user: str = "ops"
    ssh_key: str | None = None
    tags: list[str] = field(default_factory=list)
    bastion: str | None = None


@dataclass
class ExecResult:
    host: str
    command: str
    stdout: str
    stderr: str
    rc: int
    timed_out: bool = False


@dataclass
class CheckResult:
    host: str
    check_name: str
    status: Status
    value: dict
    raw: str = ""


@dataclass
class Verdict:
    decision: Decision
    reason: str = ""

    @property
    def is_auto_allow(self) -> bool:
        return self.decision is Decision.AUTO_ALLOW

    @property
    def is_deny(self) -> bool:
        return self.decision is Decision.DENY

    @property
    def requires_approval(self) -> bool:
        return self.decision is Decision.REQUIRE_APPROVAL


@dataclass
class Check:
    name: str
    command: str                       # must pass the read-only allowlist
    parse: callable                    # (stdout:str) -> dict
    evaluate: callable                 # (value:dict) -> Status
