#!/bin/bash
# Store a new memory
# Usage: memory-store.sh --agent wit --type episodic --content "..." --importance 0.7

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Load secrets and activate venv
source ~/.dotfiles/.secrets.env 2>/dev/null || true
source "$SKILL_DIR/.venv/bin/activate" 2>/dev/null || true

python3 "$SCRIPT_DIR/memory-utils.py" store "$@"
