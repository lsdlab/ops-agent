#!/bin/bash
# ops-agent managed-machine bootstrap
# ====================================
# Run this ONCE on every Linux machine you want ops-agent to manage.
#
# Usage (pick one):
#   1. Direct:  chmod +x bootstrap.sh && sudo ./bootstrap.sh
#   2. Curl:    curl -sSL http://your-central-box/bootstrap.sh | sudo bash
#   3. Remote:  ssh root@host 'bash -s' < bootstrap.sh
#
# The script will:
#   - Create the 'ops' user (if missing)
#   - Add your SSH public key to ~ops/.ssh/authorized_keys
#   - Set correct permissions on ~ops/.ssh
#   - Optionally add a sudoers snippet for read-only inspection commands
#
# You must provide the public key contents somehow:
#   - Set PUBKEY env var, OR
#   - Pipe it on stdin: echo "ssh-ed25519 AAAAC3..." | sudo ./bootstrap.sh
set -euo pipefail

OPS_USER="${OPS_USER:-ops}"
SUDO_CMDS="${SUDO_CMDS:-/usr/sbin/ss,/usr/bin/systemctl,/usr/sbin/lsof,/bin/ss,/sbin/ss}"

# ---- Resolve the public key ----
if [[ -n "${PUBKEY:-}" ]]; then
    KEY="$PUBKEY"
elif [[ ! -t 0 ]]; then
    KEY="$(cat)"
else
    echo "ERROR: No public key provided."
    echo "  Set PUBKEY='ssh-ed25519 AAAAC3...' or pipe it on stdin."
    echo "  Example: curl ... | sudo bash -s <<< \"\$(cat ~/.ssh/id_ed25519.pub)\""
    exit 1
fi

# Sanity check
if ! echo "$KEY" | grep -qE '^(ssh-(ed25519|rsa|ecdsa)|ecdsa-sha2-)'; then
    echo "ERROR: The provided key doesn't look like an SSH public key."
    echo "  Received: ${KEY:0:60}..."
    exit 1
fi

echo "==> ops-agent bootstrap (user=$OPS_USER)"

# ---- Create ops user ----
if id "$OPS_USER" &>/dev/null; then
    echo "  [skip] user '$OPS_USER' already exists"
else
    useradd -m -s /bin/bash "$OPS_USER"
    echo "  [ok] user '$OPS_USER' created"
fi

# ---- SSH authorized_keys ----
SSH_DIR="/home/$OPS_USER/.ssh"
mkdir -p "$SSH_DIR"
echo "$KEY" > "$SSH_DIR/authorized_keys"
chmod 700 "$SSH_DIR"
chmod 600 "$SSH_DIR/authorized_keys"
chown -R "$OPS_USER:$OPS_USER" "$SSH_DIR"
echo "  [ok] SSH key installed for $OPS_USER"

# ---- Optional sudoers ----
if [[ "${SKIP_SUDO:-0}" != "1" ]]; then
    SUDO_FILE="/etc/sudoers.d/ops-agent"
    IFS=',' read -ra CMDS <<< "$SUDO_CMDS"
    SUDO_LINE="$OPS_USER ALL=(ALL) NOPASSWD:"
    for c in "${CMDS[@]}"; do
        SUDO_LINE="$SUDO_LINE $c,"
    done
    SUDO_LINE="${SUDO_LINE%,}"   # strip trailing comma
    echo "$SUDO_LINE" > "$SUDO_FILE"
    chmod 440 "$SUDO_FILE"
    echo "  [ok] sudoers snippet written to $SUDO_FILE"
    echo "       (commands: $SUDO_CMDS)"
    echo "       Set SKIP_SUDO=1 to skip this step."
fi

# ---- Verify ----
if ssh-keygen -l -f "$SSH_DIR/authorized_keys" &>/dev/null; then
    echo "  [ok] key fingerprint verified"
fi

echo "==> Done. Central box can now SSH as $OPS_USER@$(hostname)"
