#!/bin/bash
# Run memory consolidation (heartbeat routine)
# Usage: memory-consolidate.sh --agent wit

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Load secrets and activate venv
source ~/.dotfiles/.secrets.env 2>/dev/null || true
source "$SKILL_DIR/.venv/bin/activate" 2>/dev/null || true

python3 "$SCRIPT_DIR/memory-utils.py" consolidate "$@"
