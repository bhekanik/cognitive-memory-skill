# Model Configuration for Memory Operations

## Current State

The memory consolidation system currently uses:
- **No LLM calls** — Pure mathematical operations (decay, retention, vector search)
- **OpenAI embeddings only** — `text-embedding-3-small` for semantic search

## Future LLM Features (when implemented)

When adding LLM-based features, use model selection:

### Use **Haiku** (cheap, fast) for:
- **Memory compression** — Summarizing 5+ similar fading memories into gist
- **Importance scoring** — Deciding significance from daily files
- **Topic extraction** — Pulling keywords/themes
- **Basic categorization** — Episodic vs semantic vs procedural

**Cost:** $0.25/M input, $1.25/M output (12x cheaper than Sonnet)

### Use **Sonnet** (smart, expensive) for:
- Active conversation
- Complex reasoning tasks
- Decisions requiring judgment
- Cross-memory synthesis

**Cost:** $3/M input, $15/M output

## Implementation Pattern

When adding LLM calls to `memory-utils.py`:

```python
import anthropic

def get_anthropic_client(model: str = "claude-haiku-4"):
    """Get Anthropic client with configurable model."""
    return anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def compress_memories(memories: List[Dict], model: str = "claude-haiku-4") -> str:
    """Compress multiple similar memories into one summary."""
    client = get_anthropic_client()
    
    prompt = f"Compress these {len(memories)} similar memories into one concise summary..."
    
    response = client.messages.create(
        model=model,  # "claude-haiku-4" for consolidation
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500
    )
    
    return response.content[0].text
```

## Environment Variables

Add to `~/.dotfiles/.secrets.env`:
```bash
ANTHROPIC_API_KEY="sk-ant-..."  # For Haiku/Sonnet calls
OPENAI_API_KEY="sk-proj-..."    # For embeddings
MEMORY_DB_URL="postgresql://..." # Database
```

---

**Note:** As of 2026-02-10, consolidation is purely computational. When LLM features are added, default to Haiku for all background memory operations.

— Shallan & Wit
