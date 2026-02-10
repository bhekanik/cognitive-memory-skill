# Heartbeat Integration

Add this to your agent's heartbeat routine (e.g., `HEARTBEAT.md`):

```markdown
## Memory Maintenance (Every Heartbeat)

1. **Consolidate daily memories**
   ```bash
   ./skills/cognitive-memory/scripts/memory-consolidate.sh --agent wit
   ```

2. **Check consolidation output for:**
   - `promotion_candidates`: High-stability memories to add to MEMORY.md
   - `decayed`: Memories that have faded significantly
   - `compressed`: Memory clusters that were summarized

3. **Surface proactive memories** if conversation context triggers strong associations
```

## Example Heartbeat Script

```bash
#!/bin/bash
# Memory maintenance during heartbeat

AGENT_ID="${AGENT_ID:-wit}"
SKILL_DIR="/path/to/skills/cognitive-memory"

# Run consolidation
result=$("$SKILL_DIR/scripts/memory-consolidate.sh" --agent "$AGENT_ID")

# Check for promotion candidates
promotions=$(echo "$result" | jq -r '.promotion_candidates | length')
if [ "$promotions" -gt 0 ]; then
    echo "📝 $promotions memories ready for promotion to MEMORY.md"
    echo "$result" | jq -r '.promotion_candidates[] | "  - \(.content[:80])..."'
fi

# Check for heavily decayed memories
decayed=$(echo "$result" | jq -r '.decayed | length')
if [ "$decayed" -gt 10 ]; then
    echo "⚠️ $decayed memories have significantly faded"
fi
```

## Proactive Memory Surfacing

During conversations, proactively retrieve relevant memories:

```python
# In your agent's conversation handler
def handle_message(message):
    # Retrieve memories relevant to current topic
    memories = retrieve_memories(
        agent_id="wit",
        query=message.content,
        limit=3,
        include_associations=True
    )
    
    # Include high-relevance memories in context
    if memories['memories'] and memories['memories'][0]['similarity'] > 0.7:
        context = f"[Memory: {memories['memories'][0]['content']}]"
        # ... include in prompt
    
    # Surface surprising associations
    if memories['associations']:
        for assoc in memories['associations']:
            if assoc['link_strength'] > 0.5:
                # This might be an interesting connection
                pass
```

## Cron Schedule

For automated maintenance, add a cron job:

```bash
# Every 30 minutes during waking hours
*/30 6-23 * * * /path/to/skills/cognitive-memory/scripts/memory-consolidate.sh --agent wit >> /tmp/memory-consolidate.log 2>&1
```
