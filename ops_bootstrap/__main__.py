"""ops-bootstrap: one-shot setup for managed machines.

Reads hosts from inventory, SSH's to each one (using current user's ssh
or a bootstrap key), and runs bootstrap.sh to create the 'ops' user,
install the ops-agent SSH key, and configure sudoers.

Example usage:
    ops-bootstrap config.yaml                          # all hosts
    ops-bootstrap config.yaml --tag prod               # prod hosts only
    ops-bootstrap config.yaml --hosts web-1 db-1        # specific hosts
    ops-bootstrap config.yaml --key ~/.ssh/admin_key    # bootstrap with admin key
    ops-bootstrap config.yaml --user root               # bootstrap as root
    ops-bootstrap config.yaml --skip-sudo               # don't configure sudoers
    ops-bootstrap config.yaml --dry-run                  # just print what would be done
"""

from __future__ import annotations
import argparse
import asyncio
import shlex
import sys
from pathlib import Path


# The bootstrap script is embedded here so ops-bootstrap works when the
# package is installed (no dependency on a separate scripts/ file).
_BOOTSTRAP_SCRIPT = r"""#!/bin/bash
# ops-agent managed-machine bootstrap
# ====================================
# Run this ONCE on every Linux machine you want ops-agent to manage.
#
# Usage (pick one):
#   1. Direct:  chmod +x bootstrap.sh && sudo ./bootstrap.sh
#   2. Curl:    curl -sSL http://your-central-box/bootstrap.sh | sudo bash
#   3. Remote:  ssh root@host 'bash -s' < bootstrap.sh
set -euo pipefail

OPS_USER="${OPS_USER:-ops}"
SUDO_CMDS="${SUDO_CMDS:-/usr/sbin/ss,/usr/bin/systemctl,/usr/sbin/lsof,/bin/ss,/sbin/ss}"

if [[ -n "${PUBKEY:-}" ]]; then
    KEY="$PUBKEY"
elif [[ ! -t 0 ]]; then
    KEY="$(cat)"
else
    echo "ERROR: No public key provided."
    echo "  Set PUBKEY='ssh-ed25519 AAAAC3...' or pipe it on stdin."
    exit 1
fi

if ! echo "$KEY" | grep -qE '^(ssh-(ed25519|rsa|ecdsa)|ecdsa-sha2-)'; then
    echo "ERROR: The provided key doesn't look like an SSH public key."
    exit 1
fi

echo "==> ops-agent bootstrap (user=$OPS_USER)"

if id "$OPS_USER" &>/dev/null; then
    echo "  [skip] user '$OPS_USER' already exists"
else
    useradd -m -s /bin/bash "$OPS_USER"
    echo "  [ok] user '$OPS_USER' created"
fi

SSH_DIR="/home/$OPS_USER/.ssh"
mkdir -p "$SSH_DIR"
echo "$KEY" > "$SSH_DIR/authorized_keys"
chmod 700 "$SSH_DIR"
chmod 600 "$SSH_DIR/authorized_keys"
chown -R "$OPS_USER:$OPS_USER" "$SSH_DIR"
echo "  [ok] SSH key installed for $OPS_USER"

if [[ "${SKIP_SUDO:-0}" != "1" ]]; then
    SUDO_FILE="/etc/sudoers.d/ops-agent"
    IFS=',' read -ra CMDS <<< "$SUDO_CMDS"
    SUDO_LINE="$OPS_USER ALL=(ALL) NOPASSWD:"
    for c in "${CMDS[@]}"; do
        SUDO_LINE="$SUDO_LINE $c,"
    done
    SUDO_LINE="${SUDO_LINE%,}"
    echo "$SUDO_LINE" > "$SUDO_FILE"
    chmod 440 "$SUDO_FILE"
    echo "  [ok] sudoers snippet written to $SUDO_FILE"
fi

echo "==> Done. Central box can now SSH as $OPS_USER@$(hostname)"
"""


def _parse_args():
    p = argparse.ArgumentParser(description="Bootstrap managed machines for ops-agent")
    p.add_argument("config", help="Path to config.yaml")
    p.add_argument("--tag", help="Only bootstrap hosts with this tag")
    p.add_argument("--hosts", nargs="*", help="Only bootstrap these host aliases")
    p.add_argument("--key", help="SSH private key for the bootstrap connection "
                   "(default: use ssh-agent)")
    p.add_argument("--user", default="root",
                   help="SSH user for the bootstrap connection (default: root)")
    p.add_argument("--port", type=int, default=22,
                   help="SSH port for the bootstrap connection (default: 22)")
    p.add_argument("--pubkey", help="Public key to install on managed machines "
                   "(default: derive from --key if possible, otherwise read from stdin)")
    p.add_argument("--skip-sudo", action="store_true",
                   help="Don't configure sudoers on managed machines")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would be done without doing it")
    return p.parse_args()


_FALLBACK_HINT = """
If you don't have root SSH access to this machine, give this one-liner to
whoever does have root on {host}:

  echo "ssh-ed25519 AAAAC3..." | sudo bash -s < scripts/bootstrap.sh

(Replace the key with the public key you want ops-agent to use.)
"""


async def _bootstrap_one(host_alias: str, address: str, args, pubkey: str) -> bool:
    """Run bootstrap.sh on a single machine via SSH.  Returns True on success."""
    ssh_cmd = [
        "ssh", "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=15",
        "-p", str(args.port),
    ]
    if args.key:
        ssh_cmd += ["-i", args.key]
    ssh_cmd += [f"{args.user}@{address}"]

    env_vars = []
    if args.skip_sudo:
        env_vars.append("SKIP_SUDO=1")
    env_prefix = " ".join(env_vars) + " " if env_vars else ""

    remote_cmd = f"{env_prefix}sudo PUBKEY={shlex.quote(pubkey)} bash -s"

    print(f"\n--- {host_alias} ({address}) ---", file=sys.stderr)
    if args.dry_run:
        print(f"  [dry-run] would run: {shlex.join(ssh_cmd)} {shlex.quote(remote_cmd)} < bootstrap.sh")
        return True

    try:
        proc = await asyncio.create_subprocess_exec(
            *ssh_cmd, remote_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=_BOOTSTRAP_SCRIPT.encode()),
            timeout=60.0,
        )
        out = stdout.decode(errors="replace")
        err = stderr.decode(errors="replace")
        if err.strip():
            print(f"  [stderr] {err.strip()}", file=sys.stderr)
        print(f"  {out.strip()}")
        if proc.returncode == 0:
            print(f"  [ok] {host_alias} bootstrapped successfully", file=sys.stderr)
            return True
        else:
            print(f"  [FAIL] {host_alias} exited with code {proc.returncode}", file=sys.stderr)
            if proc.returncode == 255:
                print(_FALLBACK_HINT.format(host=host_alias), file=sys.stderr)
            return False
    except asyncio.TimeoutError:
        print(f"  [FAIL] {host_alias} timed out (maybe SSH port blocked?)", file=sys.stderr)
        print(_FALLBACK_HINT.format(host=host_alias), file=sys.stderr)
        return False
    except FileNotFoundError:
        print(f"  [FAIL] {host_alias}: 'ssh' command not found", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"  [FAIL] {host_alias}: {exc}", file=sys.stderr)
        print(_FALLBACK_HINT.format(host=host_alias), file=sys.stderr)
        return False


async def _amain() -> None:
    args = _parse_args()

    from ops_core.config import load_config
    from ops_core.inventory import load_hosts, filter_hosts

    cfg = load_config(args.config)
    hosts = load_hosts(cfg.inventory)

    if args.tag:
        hosts = filter_hosts(hosts, tag=args.tag)
    if args.hosts:
        hosts = [h for h in hosts if h.alias in args.hosts]

    if not hosts:
        print("No hosts matched.", file=sys.stderr)
        sys.exit(1)

    # --- Resolve the public key ---
    pubkey = args.pubkey
    if not pubkey:
        # Try to derive from the private key
        key_path = args.key
        if key_path:
            pub_path = Path(key_path + ".pub")
            if pub_path.exists():
                pubkey = pub_path.read_text().strip()
        if not pubkey and not sys.stdin.isatty():
            pubkey = sys.stdin.read().strip()
        if not pubkey:
            print("ERROR: Could not determine public key.", file=sys.stderr)
            print("  Provide it with --pubkey or pipe it on stdin.", file=sys.stderr)
            print("  Example: ops-bootstrap config.yaml --key ~/.ssh/id_ed25519", file=sys.stderr)
            print("           cat ~/.ssh/id_ed25519.pub | ops-bootstrap config.yaml", file=sys.stderr)
            sys.exit(1)

    print(f"Bootstrapping {len(hosts)} host(s) ...", file=sys.stderr)
    print(f"  Public key: {pubkey[:60]}...", file=sys.stderr)
    if args.dry_run:
        print("  DRY RUN — no changes will be made", file=sys.stderr)

    # Bootstrap in parallel
    sem = asyncio.Semaphore(cfg.concurrency)

    async def one(h):
        async with sem:
            return await _bootstrap_one(h.alias, h.address, args, pubkey)

    results = await asyncio.gather(*(one(h) for h in hosts))
    ok = sum(1 for r in results if r)
    fail = len(results) - ok
    print(f"\nDone: {ok} ok, {fail} failed", file=sys.stderr)
    if fail:
        sys.exit(1)


def main() -> None:
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
