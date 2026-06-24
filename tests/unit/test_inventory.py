from pathlib import Path
import textwrap
from ops_core.inventory import load_hosts, filter_hosts
from ops_core.models import Host

HOSTS_YAML = textwrap.dedent("""
    hosts:
      - alias: web-1
        address: 10.0.0.11
        tags: [web, prod]
      - alias: db-1
        address: 10.0.0.21
        port: 2222
        tags: [db, prod]
""")


def test_load_hosts(tmp_path: Path):
    p = tmp_path / "hosts.yaml"
    p.write_text(HOSTS_YAML)
    hosts = load_hosts(p)
    assert len(hosts) == 2
    assert hosts[0].alias == "web-1"
    assert hosts[1].port == 2222


def test_filter_by_tag():
    hosts = [
        Host(alias="web-1", address="a", tags=["web", "prod"]),
        Host(alias="db-1", address="b", tags=["db", "prod"]),
    ]
    assert [h.alias for h in filter_hosts(hosts, tag="db")] == ["db-1"]
    assert [h.alias for h in filter_hosts(hosts, tag="prod")] == ["web-1", "db-1"]


def test_filter_by_alias():
    hosts = [Host(alias="web-1", address="a"), Host(alias="db-1", address="b")]
    assert [h.alias for h in filter_hosts(hosts, alias="web-1")] == ["web-1"]
