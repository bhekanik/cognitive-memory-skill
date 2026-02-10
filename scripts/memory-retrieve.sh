#!/bin/bash
# Retrieve memories by semantic search
# Usage: memory-retrieve.sh --agent wit --query "memory system" --limit 5

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Load secrets and activate venv
source ~/.dotfiles/.secrets.env 2>/dev/null || true
source "$SKILL_DIR/.venv/bin/activate" 2>/dev/null || true

python3 "$SCRIPT_DIR/memory-utils.py" retrieve "$@"
