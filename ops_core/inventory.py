from __future__ import annotations
from pathlib import Path
import yaml
from ops_core.models import Host


def load_hosts(path: str | Path) -> list[Host]:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    out: list[Host] = []
    for row in raw.get("hosts") or []:
        # Coerce string fields: an unquoted YAML scalar like `alias: 210`
        # parses as an int, which breaks str-concatenation in the web
        # templates and rich tables downstream.
        out.append(Host(
            alias=str(row["alias"]),
            address=str(row["address"]),
            port=int(row.get("port", 22)),
            user=str(row.get("user", "ops")),
            ssh_key=row.get("ssh_key"),
            tags=[str(t) for t in (row.get("tags") or [])],
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
