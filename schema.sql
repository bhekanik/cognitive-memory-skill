-- Cognitive Memory System Schema
-- Human-modeled memory with decay, reinforcement, and associative linking

-- Enable vector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- Main memories table
CREATE TABLE IF NOT EXISTS memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id VARCHAR(50) NOT NULL,  -- 'wit', 'shallan', etc.
    
    -- Content
    content TEXT NOT NULL,
    embedding vector(1536),  -- text-embedding-3-small dimensions
    
    -- Classification
    memory_type VARCHAR(20) NOT NULL 
        CHECK (memory_type IN ('episodic', 'semantic', 'procedural')),
    topics TEXT[] DEFAULT '{}',
    
    -- Temporal
    created_at TIMESTAMPTZ DEFAULT NOW(),
    event_date DATE,  -- when the event actually happened (for episodic)
    expires_at DATE,  -- for date-bound memories
    
    -- Decay mechanics
    importance FLOAT DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
    stability FLOAT DEFAULT 0.3 CHECK (stability BETWEEN 0 AND 1),
    last_accessed TIMESTAMPTZ DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    
    -- Context
    source_channel VARCHAR(50),
    source_session VARCHAR(100),
    
    -- Compression
    is_summary BOOLEAN DEFAULT FALSE,
    summarizes UUID[] DEFAULT '{}',  -- IDs of memories this summarizes
    is_deleted BOOLEAN DEFAULT FALSE  -- soft delete for compressed memories
);

-- Associative links between memories (the memory graph)
CREATE TABLE IF NOT EXISTS memory_links (
    source_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    target_id UUID REFERENCES memories(id) ON DELETE CASCADE,
    strength FLOAT DEFAULT 0.5 CHECK (strength BETWEEN 0 AND 1),
    link_type VARCHAR(20) DEFAULT 'association',  -- 'association', 'temporal', 'causal'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (source_id, target_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS memories_agent_idx ON memories(agent_id);
CREATE INDEX IF NOT EXISTS memories_type_idx ON memories(memory_type);
CREATE INDEX IF NOT EXISTS memories_topics_idx ON memories USING GIN(topics);
CREATE INDEX IF NOT EXISTS memories_created_idx ON memories(created_at DESC);
CREATE INDEX IF NOT EXISTS memories_active_idx ON memories(agent_id, is_deleted) 
    WHERE is_deleted = FALSE;

-- Vector index for semantic search (IVFFlat for good balance of speed/accuracy)
-- Only create if there are enough rows, otherwise use exact search
CREATE INDEX IF NOT EXISTS memories_embedding_idx ON memories 
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Links indexes
CREATE INDEX IF NOT EXISTS memory_links_source_idx ON memory_links(source_id);
CREATE INDEX IF NOT EXISTS memory_links_target_idx ON memory_links(target_id);

-- Retention calculation function
-- Returns a value between 0 and 1 representing how "remembered" a memory is
CREATE OR REPLACE FUNCTION calculate_retention(
    p_stability FLOAT,
    p_importance FLOAT,
    p_last_accessed TIMESTAMPTZ
) RETURNS FLOAT AS $$
DECLARE
    days_elapsed FLOAT;
    importance_boost FLOAT;
    decay_constant FLOAT;
BEGIN
    days_elapsed := EXTRACT(EPOCH FROM (NOW() - p_last_accessed)) / 86400.0;
    importance_boost := 1.0 + (p_importance * 2.0);
    decay_constant := p_stability * importance_boost * 30.0;  -- 30 days base half-life
    
    -- Clamp to reasonable values
    IF decay_constant < 1 THEN
        decay_constant := 1;
    END IF;
    
    RETURN GREATEST(0, LEAST(1, EXP(-days_elapsed / decay_constant)));
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Convenience view for active memories with retention
CREATE OR REPLACE VIEW active_memories AS
SELECT 
    *,
    calculate_retention(stability, importance, last_accessed) as retention
FROM memories
WHERE is_deleted = FALSE;

-- Function to reinforce a memory (called on retrieval)
CREATE OR REPLACE FUNCTION reinforce_memory(
    p_memory_id UUID
) RETURNS VOID AS $$
DECLARE
    days_since_access FLOAT;
    spacing_bonus FLOAT;
    current_stability FLOAT;
BEGIN
    -- Get current stability and calculate spacing bonus
    SELECT 
        stability,
        EXTRACT(EPOCH FROM (NOW() - last_accessed)) / 86400.0
    INTO current_stability, days_since_access
    FROM memories 
    WHERE id = p_memory_id;
    
    -- Spacing bonus: longer gaps = bigger stability increase (spaced repetition)
    spacing_bonus := LEAST(2.0, days_since_access / 7.0);
    
    -- Update the memory
    UPDATE memories SET
        last_accessed = NOW(),
        access_count = access_count + 1,
        stability = LEAST(1.0, current_stability + 0.1 * spacing_bonus)
    WHERE id = p_memory_id;
END;
$$ LANGUAGE plpgsql;

-- Function to strengthen link between two memories
CREATE OR REPLACE FUNCTION strengthen_link(
    p_source_id UUID,
    p_target_id UUID,
    p_increment FLOAT DEFAULT 0.1
) RETURNS VOID AS $$
BEGIN
    INSERT INTO memory_links (source_id, target_id, strength)
    VALUES (p_source_id, p_target_id, 0.5)
    ON CONFLICT (source_id, target_id) DO UPDATE SET
        strength = LEAST(1.0, memory_links.strength + p_increment),
        updated_at = NOW();
        
    -- Also create reverse link (memories are bidirectionally associated)
    INSERT INTO memory_links (source_id, target_id, strength)
    VALUES (p_target_id, p_source_id, 0.5)
    ON CONFLICT (source_id, target_id) DO UPDATE SET
        strength = LEAST(1.0, memory_links.strength + p_increment),
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;
