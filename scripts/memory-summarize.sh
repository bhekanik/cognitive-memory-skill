#!/bin/bash
# Summarize multiple memories into one gist

set -euo pipefail

if [ $# -lt 2 ]; then
    echo "Usage: $0 <agent_id> <memory_id_1> [memory_id_2] [memory_id_3] ..."
    echo "Example: $0 shallan abc123 def456 ghi789"
    exit 1
fi

AGENT="$1"
shift
IDS=("$@")

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

# Run summarization
python3 "$SCRIPT_DIR/memory-utils.py" summarize \
    --agent "$AGENT" \
    --ids "${IDS[@]}"
