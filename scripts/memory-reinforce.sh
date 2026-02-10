#!/bin/bash
# Reinforce a memory (call after retrieval to strengthen it)
# Usage: memory-reinforce.sh <memory-uuid>

if [ -z "$1" ]; then
    echo "Usage: memory-reinforce.sh <memory-uuid>"
    exit 1
fi

if [ -z "$MEMORY_DB_URL" ]; then
    echo "Error: MEMORY_DB_URL not set"
    exit 1
fi

psql "$MEMORY_DB_URL" -c "SELECT reinforce_memory('$1'::uuid);"
echo "✓ Memory reinforced: $1"
