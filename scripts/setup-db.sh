#!/bin/bash
# Setup Cognitive Memory database schema
# Requires: MEMORY_DB_URL environment variable

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

if [ -z "$MEMORY_DB_URL" ]; then
    echo "Error: MEMORY_DB_URL environment variable not set"
    echo "Example: export MEMORY_DB_URL='postgresql://user:pass@host:5432/dbname'"
    exit 1
fi

echo "Setting up Cognitive Memory schema..."
echo "Database: ${MEMORY_DB_URL%%@*}@..."

# Run schema
psql "$MEMORY_DB_URL" -f "$SKILL_DIR/schema.sql"

echo "✓ Schema created successfully"
echo ""
echo "Tables created:"
psql "$MEMORY_DB_URL" -c "\dt memories*" 2>/dev/null || true
psql "$MEMORY_DB_URL" -c "\dt memory_links*" 2>/dev/null || true
echo ""
echo "Ready to use! Test with:"
echo "  ./scripts/memory-utils.py store --agent wit --content 'Test memory'"
