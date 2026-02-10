#!/usr/bin/env python3
"""
Cognitive Memory System - Python Utilities
Handles embeddings, storage, retrieval, and consolidation.
"""

import os
import sys
import json
import argparse
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import math

# Third-party imports (install: pip install openai anthropic psycopg2-binary pgvector)
try:
    import openai
    import anthropic
    import psycopg2
    from psycopg2.extras import RealDictCursor, Json
    from pgvector.psycopg2 import register_vector
except ImportError as e:
    print(f"Missing dependency: {e}", file=sys.stderr)
    print("Install with: pip install openai anthropic psycopg2-binary pgvector", file=sys.stderr)
    sys.exit(1)


def get_db_connection():
    """Get database connection from environment."""
    db_url = os.environ.get('MEMORY_DB_URL')
    if not db_url:
        raise ValueError("MEMORY_DB_URL environment variable not set")
    
    conn = psycopg2.connect(db_url)
    register_vector(conn)
    return conn


def get_embedding(text: str, model: str = "text-embedding-3-small") -> List[float]:
    """Generate embedding for text using OpenAI."""
    client = openai.OpenAI()
    response = client.embeddings.create(
        input=text,
        model=model
    )
    return response.data[0].embedding


def calculate_retention(stability: float, importance: float, last_accessed: datetime) -> float:
    """Calculate current retention level (0-1) for a memory."""
    days_elapsed = (datetime.now(last_accessed.tzinfo) - last_accessed).total_seconds() / 86400
    importance_boost = 1.0 + (importance * 2.0)
    decay_constant = stability * importance_boost * 30.0  # 30 days base
    
    if decay_constant < 1:
        decay_constant = 1
    
    return max(0, min(1, math.exp(-days_elapsed / decay_constant)))


def store_memory(
    agent_id: str,
    content: str,
    memory_type: str = "episodic",
    importance: float = None,
    topics: List[str] = None,
    event_date: str = None,
    expires_at: str = None,
    source_channel: str = None,
    source_session: str = None,
    skip_dedup: bool = False,
    dedup_threshold: float = 0.92,
    auto_score_importance: bool = False,
    auto_extract_topics: bool = False
) -> Dict[str, Any]:
    """Store a new memory with embedding.
    
    Args:
        auto_score_importance: Use LLM to auto-score importance (0-1)
        auto_extract_topics: Use LLM to auto-extract topics from content
    """
    
    # Auto-score importance if requested
    if auto_score_importance and importance is None:
        importance = score_importance(content)
    elif importance is None:
        importance = 0.5
    
    # Auto-extract topics if requested
    if auto_extract_topics and not topics:
        topics = extract_topics(content)
    elif not topics:
        topics = []
    
    # Generate embedding
    embedding = get_embedding(content)
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Check for similar existing memory (deduplication)
        if not skip_dedup:
            cur.execute("""
                SELECT id, content, 
                       1 - (embedding <=> %s::vector) as similarity
                FROM memories
                WHERE agent_id = %s
                  AND is_deleted = FALSE
                  AND 1 - (embedding <=> %s::vector) > %s
                ORDER BY similarity DESC
                LIMIT 1
            """, (embedding, agent_id, embedding, dedup_threshold))
            
            similar = cur.fetchone()
            if similar:
                # Reinforce existing memory instead of duplicating
                cur.execute("SELECT reinforce_memory(%s)", (similar['id'],))
                conn.commit()
                return {
                    "action": "reinforced",
                    "id": str(similar['id']),
                    "existing_content": similar['content'],
                    "similarity": similar['similarity']
                }
        
        # Insert new memory
        cur.execute("""
            INSERT INTO memories (
                agent_id, content, embedding, memory_type, importance,
                topics, event_date, expires_at, source_channel, source_session
            ) VALUES (
                %s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s
            )
            RETURNING id, created_at
        """, (
            agent_id, content, embedding, memory_type, importance,
            topics, event_date, expires_at, source_channel, source_session
        ))
        
        result = cur.fetchone()
        conn.commit()
        
        return {
            "action": "created",
            "id": str(result['id']),
            "created_at": result['created_at'].isoformat()
        }
        
    finally:
        cur.close()
        conn.close()


def retrieve_memories(
    agent_id: str,
    query: str,
    limit: int = 5,
    include_associations: bool = True,
    min_retention: float = 0.2,
    memory_types: List[str] = None
) -> Dict[str, Any]:
    """Retrieve memories by semantic similarity, weighted by retention."""
    
    # Generate query embedding
    query_embedding = get_embedding(query)
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Build type filter
        type_filter = ""
        if memory_types:
            type_filter = f"AND memory_type IN ({','.join(['%s'] * len(memory_types))})"
        
        # Semantic search with retention weighting
        query_sql = f"""
            SELECT 
                id, content, memory_type, topics, importance, stability,
                created_at, event_date, last_accessed, access_count,
                1 - (embedding <=> %s::vector) as similarity,
                calculate_retention(stability, importance, last_accessed) as retention
            FROM memories
            WHERE agent_id = %s
              AND is_deleted = FALSE
              AND calculate_retention(stability, importance, last_accessed) > %s
              {type_filter}
            ORDER BY 
                (1 - (embedding <=> %s::vector)) * 
                calculate_retention(stability, importance, last_accessed) DESC
            LIMIT %s
        """
        
        params = [query_embedding, agent_id, min_retention]
        if memory_types:
            params.extend(memory_types)
        params.extend([query_embedding, limit])
        
        cur.execute(query_sql, params)
        memories = cur.fetchall()
        
        # Reinforce retrieved memories
        retrieved_ids = []
        for mem in memories:
            cur.execute("SELECT reinforce_memory(%s)", (mem['id'],))
            retrieved_ids.append(mem['id'])
        
        # Get associated memories
        associations = []
        if include_associations and retrieved_ids:
            cur.execute("""
                SELECT DISTINCT ON (m.id)
                    m.id, m.content, m.memory_type, m.topics, m.importance,
                    l.strength as link_strength,
                    calculate_retention(m.stability, m.importance, m.last_accessed) as retention
                FROM memories m
                JOIN memory_links l ON m.id = l.target_id
                WHERE l.source_id = ANY(%s::uuid[])
                  AND m.id != ALL(%s::uuid[])
                  AND m.is_deleted = FALSE
                  AND l.strength > 0.3
                ORDER BY m.id, l.strength DESC
                LIMIT %s
            """, (retrieved_ids, retrieved_ids, limit))
            
            associations = cur.fetchall()
            
            # Reinforce associated memories (weaker reinforcement)
            for assoc in associations:
                cur.execute("SELECT reinforce_memory(%s)", (assoc['id'],))
        
        conn.commit()
        
        # Convert to serializable format
        def serialize_row(row):
            result = dict(row)
            for key, value in result.items():
                if isinstance(value, datetime):
                    result[key] = value.isoformat()
                elif hasattr(value, '__iter__') and not isinstance(value, (str, list)):
                    result[key] = list(value)
            return result
        
        return {
            "memories": [serialize_row(m) for m in memories],
            "associations": [serialize_row(a) for a in associations],
            "query": query,
            "retrieved_count": len(memories),
            "association_count": len(associations)
        }
        
    finally:
        cur.close()
        conn.close()


def extract_topics(text: str, max_topics: int = 5) -> List[str]:
    """Extract keywords/topics from text using gpt-5-mini."""
    client = openai.OpenAI()
    
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": "Extract 3-5 key topics/keywords from this text. Return ONLY a comma-separated list, no explanation."},
            {"role": "user", "content": text}
        ],
        max_completion_tokens=500
    )
    
    topics_text = response.choices[0].message.content.strip()
    topics = [t.strip() for t in topics_text.split(',') if t.strip()]
    return topics[:max_topics]


def score_importance(text: str, context: str = "") -> float:
    """Auto-score importance (0-1) based on content significance using gpt-5-mini."""
    client = openai.OpenAI()
    
    prompt = f"""Rate the importance of this memory on a scale of 0.0 to 1.0, where:
- 0.0-0.3: Trivial/routine (weather, small talk)
- 0.4-0.6: Moderate (preferences, daily events)
- 0.7-0.9: Important (decisions, relationships, learnings)
- 1.0: Critical (life events, core beliefs, major insights)

{f'Context: {context}' if context else ''}

Memory: {text}

Return ONLY a number between 0.0 and 1.0."""

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=200
    )
    
    try:
        score = float(response.choices[0].message.content.strip())
        return max(0.0, min(1.0, score))
    except:
        return 0.5  # Default to moderate if parsing fails


def summarize_memories(memories: List[Dict[str, Any]]) -> str:
    """Compress multiple similar memories into one gist using gpt-5-mini."""
    if not memories:
        return ""
    
    if len(memories) == 1:
        return memories[0]['content']
    
    client = openai.OpenAI()
    
    # Build combined text
    memory_texts = "\n\n".join([
        f"- {m['content']} (created: {m.get('created_at', 'unknown')})"
        for m in memories
    ])
    
    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[
            {"role": "system", "content": "You are compressing multiple related memories into one coherent summary. Preserve key facts and context. Be concise but complete."},
            {"role": "user", "content": f"Summarize these {len(memories)} related memories:\n\n{memory_texts}"}
        ],
        max_completion_tokens=1500
    )
    
    return response.choices[0].message.content.strip()


def consolidate_memories(agent_id: str, compression_threshold: int = 5) -> Dict[str, Any]:
    """Run memory consolidation: decay check, compression, link strengthening."""
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    results = {
        "decayed": [],
        "compressed": [],
        "promotion_candidates": [],
        "links_created": 0
    }
    
    try:
        # 1. Find memories that have decayed significantly (retention < 0.2)
        cur.execute("""
            SELECT id, content, memory_type, topics,
                   calculate_retention(stability, importance, last_accessed) as retention,
                   created_at
            FROM memories
            WHERE agent_id = %s
              AND is_deleted = FALSE
              AND is_summary = FALSE
              AND calculate_retention(stability, importance, last_accessed) < 0.2
        """, (agent_id,))
        
        fading = cur.fetchall()
        results["decayed"] = [{"id": str(m['id']), "content": m['content'][:100], "retention": m['retention']} for m in fading]
        
        # 2. Group fading memories by topic similarity for compression
        if len(fading) >= compression_threshold:
            # Get embeddings for fading memories and cluster them
            topic_groups = {}  # topic -> [memory_ids]
            
            for mem in fading:
                for topic in (mem.get('topics') or []):
                    if topic not in topic_groups:
                        topic_groups[topic] = []
                    topic_groups[topic].append(mem)
            
            # Compress groups with 3+ similar memories
            for topic, group_mems in topic_groups.items():
                if len(group_mems) >= 3:
                    summary_text = summarize_memories(group_mems)
                    
                    # Store compressed memory
                    compressed = store_memory(
                        agent_id=agent_id,
                        content=summary_text,
                        memory_type="semantic",
                        importance=0.7,
                        topics=[topic],
                        skip_dedup=True
                    )
                    
                    # Mark originals as summarized
                    ids_to_mark = [m['id'] for m in group_mems]
                    cur.execute("""
                        UPDATE memories
                        SET is_summary = TRUE
                        WHERE id = ANY(%s::uuid[])
                    """, (ids_to_mark,))
                    
                    results["compressed"].append({
                        "topic": topic,
                        "count": len(group_mems),
                        "summary_id": compressed.get('id'),
                        "original_ids": [str(i) for i in ids_to_mark]
                    })
        
        # 3. Find high-stability memories for potential promotion to MEMORY.md
        cur.execute("""
            SELECT id, content, memory_type, topics, stability, access_count
            FROM memories
            WHERE agent_id = %s
              AND is_deleted = FALSE
              AND memory_type = 'semantic'
              AND stability > 0.9
              AND access_count > 10
        """, (agent_id,))
        
        promotion_candidates = cur.fetchall()
        results["promotion_candidates"] = [
            {"id": str(m['id']), "content": m['content'], "stability": m['stability'], "access_count": m['access_count']}
            for m in promotion_candidates
        ]
        
        # 4. Soft delete memories that have been dormant too long (retention < 0.05 for 30+ days)
        cur.execute("""
            UPDATE memories
            SET is_deleted = TRUE
            WHERE agent_id = %s
              AND is_deleted = FALSE
              AND is_summary = FALSE
              AND calculate_retention(stability, importance, last_accessed) < 0.05
              AND last_accessed < NOW() - INTERVAL '30 days'
        """, (agent_id,))
        
        conn.commit()
        
        return results
        
    finally:
        cur.close()
        conn.close()


def link_memories(source_id: str, target_id: str, strength: float = 0.5) -> Dict[str, Any]:
    """Create or strengthen a link between two memories."""
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        cur.execute("SELECT strengthen_link(%s, %s, %s)", (source_id, target_id, strength))
        conn.commit()
        return {"success": True, "source": source_id, "target": target_id}
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description="Cognitive Memory System CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Store command
    store_parser = subparsers.add_parser("store", help="Store a new memory")
    store_parser.add_argument("--agent", required=True, help="Agent ID")
    store_parser.add_argument("--content", required=True, help="Memory content")
    store_parser.add_argument("--type", default="episodic", choices=["episodic", "semantic", "procedural"])
    store_parser.add_argument("--importance", type=float, help="Importance (0-1), auto-scored if not provided")
    store_parser.add_argument("--topics", nargs="*", default=[], help="Topics, auto-extracted if not provided")
    store_parser.add_argument("--event-date", help="When the event happened (YYYY-MM-DD)")
    store_parser.add_argument("--expires", help="When memory expires (YYYY-MM-DD)")
    store_parser.add_argument("--channel", help="Source channel")
    store_parser.add_argument("--session", help="Source session")
    store_parser.add_argument("--skip-dedup", action="store_true")
    store_parser.add_argument("--auto-score", action="store_true", help="Auto-score importance using LLM")
    store_parser.add_argument("--auto-topics", action="store_true", help="Auto-extract topics using LLM")
    
    # Retrieve command
    retrieve_parser = subparsers.add_parser("retrieve", help="Retrieve memories")
    retrieve_parser.add_argument("--agent", required=True, help="Agent ID")
    retrieve_parser.add_argument("--query", required=True, help="Search query")
    retrieve_parser.add_argument("--limit", type=int, default=5)
    retrieve_parser.add_argument("--no-associations", action="store_true")
    retrieve_parser.add_argument("--min-retention", type=float, default=0.2)
    retrieve_parser.add_argument("--types", nargs="*")
    
    # Consolidate command
    consolidate_parser = subparsers.add_parser("consolidate", help="Run consolidation")
    consolidate_parser.add_argument("--agent", required=True, help="Agent ID")
    consolidate_parser.add_argument("--compression-threshold", type=int, default=5)
    
    # Link command
    link_parser = subparsers.add_parser("link", help="Link two memories")
    link_parser.add_argument("--source", required=True, help="Source memory ID")
    link_parser.add_argument("--target", required=True, help="Target memory ID")
    link_parser.add_argument("--strength", type=float, default=0.5)
    
    # Extract topics command
    topics_parser = subparsers.add_parser("extract-topics", help="Extract topics from text")
    topics_parser.add_argument("--text", required=True, help="Text to extract topics from")
    topics_parser.add_argument("--max", type=int, default=5, help="Max topics to extract")
    
    # Score importance command
    score_parser = subparsers.add_parser("score-importance", help="Score importance of text")
    score_parser.add_argument("--text", required=True, help="Text to score")
    score_parser.add_argument("--context", help="Additional context")
    
    # Summarize command
    summarize_parser = subparsers.add_parser("summarize", help="Summarize multiple memories")
    summarize_parser.add_argument("--agent", required=True, help="Agent ID")
    summarize_parser.add_argument("--ids", nargs="+", required=True, help="Memory IDs to summarize")
    
    args = parser.parse_args()
    
    if args.command == "store":
        result = store_memory(
            agent_id=args.agent,
            content=args.content,
            memory_type=args.type,
            importance=args.importance,
            topics=args.topics if args.topics else None,
            event_date=args.event_date,
            expires_at=args.expires,
            source_channel=args.channel,
            source_session=args.session,
            skip_dedup=args.skip_dedup,
            auto_score_importance=args.auto_score,
            auto_extract_topics=args.auto_topics
        )
    elif args.command == "retrieve":
        result = retrieve_memories(
            agent_id=args.agent,
            query=args.query,
            limit=args.limit,
            include_associations=not args.no_associations,
            min_retention=args.min_retention,
            memory_types=args.types
        )
    elif args.command == "consolidate":
        result = consolidate_memories(
            agent_id=args.agent,
            compression_threshold=args.compression_threshold
        )
    elif args.command == "link":
        result = link_memories(
            source_id=args.source,
            target_id=args.target,
            strength=args.strength
        )
    elif args.command == "extract-topics":
        topics = extract_topics(args.text, max_topics=args.max)
        result = {"topics": topics, "count": len(topics)}
    elif args.command == "score-importance":
        score = score_importance(args.text, context=args.context or "")
        result = {"importance": score, "text_preview": args.text[:100]}
    elif args.command == "summarize":
        # Fetch memories by IDs
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cur.execute("""
                SELECT id, content, created_at, topics
                FROM memories
                WHERE agent_id = %s AND id = ANY(%s::uuid[])
            """, (args.agent, args.ids))
            memories = cur.fetchall()
            
            if not memories:
                result = {"error": "No memories found with given IDs"}
            else:
                summary = summarize_memories([dict(m) for m in memories])
                result = {
                    "summary": summary,
                    "source_count": len(memories),
                    "source_ids": args.ids
                }
        finally:
            cur.close()
            conn.close()
    else:
        parser.print_help()
        sys.exit(1)
    
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
