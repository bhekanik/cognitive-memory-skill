#!/bin/bash
# Score importance of text using LLM (0-1 scale)

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <text> [context]"
    echo "Example: $0 'BK bought a house in Bedford' 'Major life event'"
    exit 1
fi

TEXT="$1"
CONTEXT="${2:-}"

# Load environment
if [ -f ~/.dotfiles/.secrets.env ]; then
    source ~/.dotfiles/.secrets.env
fi

if [ -z "${MEMORY_DB_URL:-}" ]; then
    echo "Error: MEMORY_DB_URL not set" >&2
    exit 1
fi

# Activate venv
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

if [ ! -d "$SKILL_DIR/.venv" ]; then
    echo "Error: Virtual environment not found. Run setup-db.sh first." >&2
    exit 1
fi

source "$SKILL_DIR/.venv/bin/activate"

# Run scoring
if [ -n "$CONTEXT" ]; then
    python3 "$SCRIPT_DIR/memory-utils.py" score-importance \
        --text "$TEXT" \
        --context "$CONTEXT"
else
    python3 "$SCRIPT_DIR/memory-utils.py" score-importance \
        --text "$TEXT"
fi
