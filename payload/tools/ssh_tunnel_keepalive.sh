#!/bin/bash
# ssh-tunnel-keepalive — hold an SSH local-forward tunnel open across a long
# session, with server keepalives and automatic reconnect on idle drop.
# Generic: any local forward (database, internal service). macOS bash 3.2 safe.
#
# Usage:
#   ssh_tunnel_keepalive.sh -k KEY -H HOST -u USER -L SPEC [-P PORT] [-o "extra ssh opts"]
#     -k  path to your private key (chmod 600)
#     -H  bastion / jump host
#     -u  ssh user on the host (defaults to $USER)
#     -L  forward spec: localport:remotehost:remoteport  (e.g. 15432:db.internal:5432)
#     -P  ssh port on the host (default 22)
#     -o  extra ssh options (optional)
#
# Example (Postgres through a bastion):
#   ssh_tunnel_keepalive.sh -k ~/.ssh/id_ed25519 -H bastion.example.com \
#       -u me -L 15432:db.internal:5432
#
# Prefers autossh when installed (robust reconnect); otherwise loops plain ssh
# with ServerAliveInterval keepalives and reconnects on drop. Never hardcode a
# host or key into a tracked file — pass them as flags or from secrets.env.
set -eu

KEY=""; HOST=""; SSH_USER="${USER:-}"; SPEC=""; PORT=22; EXTRA=""
while getopts "k:H:u:L:P:o:h" opt; do
  case "$opt" in
    k) KEY="$OPTARG" ;;
    H) HOST="$OPTARG" ;;
    u) SSH_USER="$OPTARG" ;;
    L) SPEC="$OPTARG" ;;
    P) PORT="$OPTARG" ;;
    o) EXTRA="$OPTARG" ;;
    h) grep '^#' "$0" | sed 's/^#\{1,\} \{0,1\}//'; exit 0 ;;
    *) echo "bad flag; -h for help" >&2; exit 2 ;;
  esac
done

if [ -z "$KEY" ] || [ -z "$HOST" ] || [ -z "$SPEC" ]; then
  echo "need -k KEY, -H HOST, and -L localport:remotehost:remoteport (-h for help)" >&2
  exit 2
fi
[ -r "$KEY" ] || { echo "key not readable: $KEY" >&2; exit 2; }

KEEPALIVE="-o ServerAliveInterval=30 -o ServerAliveCountMax=3 -o ExitOnForwardFailure=yes"
COMMON="-i $KEY -p $PORT -N -L $SPEC $KEEPALIVE $EXTRA"
LOCALPORT="${SPEC%%:*}"

echo "tunnel: localhost:$LOCALPORT -> ${SPEC#*:}  via $SSH_USER@$HOST:$PORT"

if command -v autossh >/dev/null 2>&1; then
  echo "using autossh (auto-reconnect)"
  # shellcheck disable=SC2086
  AUTOSSH_GATETIME=0 exec autossh -M 0 $COMMON "$SSH_USER@$HOST"
fi

echo "autossh not found — using a plain-ssh reconnect loop (Ctrl-C to stop)"
while true; do
  # shellcheck disable=SC2086
  ssh $COMMON "$SSH_USER@$HOST" || true
  echo "tunnel dropped; reconnecting in 5s..." >&2
  sleep 5
done
