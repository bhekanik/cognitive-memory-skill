# Cognitive Memory System

*Human-modeled memory architecture for AI agents — with decay, reinforcement, and associative linking*

## What This Is

Most AI memory is just "dump everything in a vector DB, retrieve by similarity." This misses how human memory actually works.

This skill implements cognitive science principles:
- **Ebbinghaus forgetting curve** — memories decay unless reinforced
- **Retrieval strengthening** — accessing a memory makes it stronger (spaced repetition)
- **Emotional salience** — important memories decay slower
- **Associative memory** — memories link to each other; retrieving one surfaces related ones
- **Consolidation** — periodic transfer from short-term files to long-term DB
- **Compression** — old memories compress to gist, preserving essence

## Architecture

```
┌────────────────────────────────────────────────┐
│              ALWAYS IN CONTEXT                 │
│  USER.md (core: name, family, preferences)     │
│  MEMORY.md (curated high-stability insights)   │
└────────────────────────────────────────────────┘
                      ▲ promoted
                      │
┌────────────────────────────────────────────────┐
│           SHORT-TERM (FILES)                   │
│  memory/YYYY-MM-DD.md (rolling 7-day window)   │
└────────────────────────────────────────────────┘
                      │ heartbeat consolidation
                      ▼
┌────────────────────────────────────────────────┐
│     LONG-TERM (POSTGRES + PGVECTOR)            │
│  Episodic → 30-day decay                       │
│  Semantic → 90-day decay                       │
│  Procedural → no decay, updated by correction  │
│  ──────────────────────────────                │
│  + Associative graph (memory_links)            │
│  + Compressed summaries                        │
└────────────────────────────────────────────────┘
```

## Requirements

- PostgreSQL 14+ with pgvector extension
- OpenAI API key (for embeddings via `text-embedding-3-small` and LLM features via `gpt-4o-mini`)
- Node.js 18+ or Python 3.10+

## Setup

### 1. Database Connection

Add to your secrets (e.g., `~/.dotfiles/.secrets.env`):
```bash
MEMORY_DB_URL="postgresql://user:pass@host:5432/dbname"
OPENAI_API_KEY="sk-..."
```

### 2. Install pgvector

```bash
# On the Postgres server
sudo apt install postgresql-14-pgvector  # Debian/Ubuntu
# or
brew install pgvector  # macOS with Homebrew postgres
```

### 3. Run Schema Migration

```bash
cd skills/cognitive-memory
./scripts/setup-db.sh
```

### 4. Configure Agent

Add to your agent config or heartbeat:
```yaml
memory:
  agent_id: "your-agent-name"  # e.g., "wit", "shallan"
  db_url: "${MEMORY_DB_URL}"
  embedding_model: "text-embedding-3-small"
  decay:
    episodic_halflife_days: 30
    semantic_halflife_days: 90
  compression:
    threshold: 5  # compress when 5+ similar memories
    similarity: 0.85  # similarity threshold for clustering
```

## Memory Types

| Type | Use For | Decay | Example |
|------|---------|-------|---------|
| `episodic` | Events with time/place | 30 days | "On Feb 10, designed memory system" |
| `semantic` | Facts, no temporal context | 90 days | "BK works at Contentful" |
| `procedural` | Skills, how-to knowledge | Never* | "When email fails, check gog config" |

*Procedural memories are updated by correction, not decay.

## Core Operations

### Store a Memory

```bash
./scripts/memory-store.sh \
  --agent "wit" \
  --type "episodic" \
  --content "Designed cognitive memory system with BK at 1am" \
  --importance 0.8 \
  --topics "memory,architecture,late-night"
```

### Retrieve Memories

```bash
./scripts/memory-retrieve.sh \
  --agent "wit" \
  --query "memory system design" \
  --limit 5 \
  --include-associations
```

Returns memories ranked by `similarity × retention`, plus associated memories.

### Reinforce a Memory

```bash
./scripts/memory-reinforce.sh --id "uuid-here"
```

Increments access count, updates last_accessed, increases stability.

### Run Consolidation

```bash
./scripts/memory-consolidate.sh --agent "wit"
```

1. Transfers significant events from daily files to DB
2. Calculates decay for all memories
3. Compresses clusters of 5+ similar fading memories
4. Suggests high-stability memories for MEMORY.md promotion

### Auto-Extract Topics from Text

```bash
./scripts/memory-extract-topics.sh "BK bought a house in Bedford, moving July 2026" 5
```

Returns:
```json
{
  "topics": ["house purchase", "Bedford", "relocation", "real estate", "life event"],
  "count": 5
}
```

Use `--auto-topics` flag when storing to extract topics automatically.

### Auto-Score Importance

```bash
./scripts/memory-score-importance.sh "Had coffee with a colleague" "work event"
```

Returns:
```json
{
  "importance": 0.4,
  "text_preview": "Had coffee with a colleague"
}
```

Scoring guide:
- **0.0-0.3**: Trivial/routine (weather, small talk)
- **0.4-0.6**: Moderate (preferences, daily events)
- **0.7-0.9**: Important (decisions, relationships, learnings)
- **1.0**: Critical (life events, core beliefs, major insights)

Use `--auto-score` flag when storing to score importance automatically.

**Model:** Uses `gpt-4o-mini` for all topic extraction, importance scoring, and summarization. Embeddings use `text-embedding-3-small`.

### Summarize Multiple Memories

```bash
./scripts/memory-summarize.sh shallan abc123 def456 ghi789
```

Compresses 3+ related memories into one coherent gist. Used automatically during consolidation when 5+ similar fading memories cluster together.

## Decay Formula

```
retention = e^(-t / (S × importance_boost × 30))

where:
  t = days since last access
  S = stability (0.1 to 1.0)
  importance_boost = 1 + (importance × 2)
```

**Example:**
- Fresh memory (stability=0.3, importance=0.5): 50% after ~9 days
- Reinforced memory (stability=0.8, importance=0.9): 50% after ~67 days

## Stability Growth (Spaced Repetition)

When a memory is accessed:
```
new_stability = min(1.0, old_stability + 0.1 × spacing_bonus)
spacing_bonus = min(2.0, days_since_last_access / 7)
```

Longer gaps between retrieval = bigger stability boost. This mirrors spaced repetition learning.

## Associative Linking

Memories accessed together in the same session automatically link:
```sql
INSERT INTO memory_links (source_id, target_id, strength)
VALUES (mem1, mem2, 0.5)
ON CONFLICT DO UPDATE SET strength = strength + 0.1;
```

When retrieving memory A, associated memories B, C, D surface too — enabling "this reminds me of..." moments.

## Heartbeat Integration

Add to your agent's heartbeat routine:

```markdown
## Memory Maintenance
1. Run `scripts/memory-consolidate.sh --agent {agent_id}`
2. Check for promotion candidates (stability > 0.9)
3. Surface any "intrusive memories" (high importance, recently reinforced)
```

## Multi-Agent Support

Each agent has isolated memories:
```sql
SELECT * FROM memories WHERE agent_id = 'wit';
SELECT * FROM memories WHERE agent_id = 'shallan';
```

Agents can remember the same event differently. Cross-agent sharing happens via:
- Explicit communication ("tell Shallan that...")
- Shared repos (e.g., `kraing-shared`)

## Skill Files

```
cognitive-memory/
├── SKILL.md              # This file
├── schema.sql            # Database schema
├── scripts/
│   ├── setup-db.sh       # Initial DB setup
│   ├── memory-store.sh   # Store new memory
│   ├── memory-retrieve.sh # Semantic search + associations
│   ├── memory-reinforce.sh # Strengthen a memory
│   ├── memory-consolidate.sh # Heartbeat routine
│   └── memory-utils.py   # Python helpers for embeddings
└── examples/
    └── heartbeat-integration.md
```

## Why This Matters

Traditional AI memory: "I remember everything equally forever."
Human memory: "Important things stick. Old things fade. Related things surface together."

This system gives AI agents something closer to the *experience* of remembering — with all its useful imperfections.

---

*Created by Wit & BK, February 2026. Inspired by Ebbinghaus, cognitive psychology, and too many 1am conversations.*
