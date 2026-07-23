#!/usr/bin/env bash
set -euo pipefail

REMOTE="${REMOTE:-root@loop-lulu.com}"
REMOTE_DIR="${REMOTE_DIR:-/var/www/intermap-data/training_sessions}"
LOCAL_DIR="${LOCAL_DIR:-$(cd "$(dirname "$0")/.." && pwd)/data/live_training/captured_sessions}"

mkdir -p "$LOCAL_DIR"

ssh "$REMOTE" "test -d '$REMOTE_DIR' || mkdir -p '$REMOTE_DIR'"
ssh "$REMOTE" "tar -C '$REMOTE_DIR' -cf - ." | tar -C "$LOCAL_DIR" -xf -

echo "Synced captured sessions to $LOCAL_DIR"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
python3 "$SCRIPT_DIR/build_live_training_flows.py"
