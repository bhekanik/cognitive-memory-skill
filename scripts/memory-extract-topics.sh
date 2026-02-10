#!/bin/bash
# Extract topics from text using LLM

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <text> [max_topics]"
    echo "Example: $0 'BK moved from Harrow to Bedford in July 2026' 5"
    exit 1
fi

TEXT="$1"
MAX="${2:-5}"

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

# Run extraction
python3 "$SCRIPT_DIR/memory-utils.py" extract-topics \
    --text "$TEXT" \
    --max "$MAX"
