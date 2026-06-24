from __future__ import annotations
from pathlib import Path
import yaml
from ops_core.models import Host


def load_hosts(path: str | Path) -> list[Host]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    out: list[Host] = []
    for row in raw.get("hosts") or []:
        out.append(Host(
            alias=row["alias"],
            address=row["address"],
            port=int(row.get("port", 22)),
            user=row.get("user", "ops"),
            ssh_key=row.get("ssh_key"),
            tags=list(row.get("tags") or []),
            bastion=row.get("bastion"),
        ))
    return out


def filter_hosts(hosts: list[Host], *, tag: str | None = None,
                 alias: str | None = None) -> list[Host]:
    result = hosts
    if tag is not None:
        result = [h for h in result if tag in h.tags]
    if alias is not None:
        result = [h for h in result if h.alias == alias]
    return result
