#!/usr/bin/env python3
"""Setup the cognitive memory database schema - v2 with proper statement handling."""

import os
import sys

try:
    import psycopg2
    from psycopg2 import sql
except ImportError:
    print("Installing psycopg2-binary...")
    os.system("pip install psycopg2-binary")
    import psycopg2

def main():
    db_url = os.environ.get('MEMORY_DB_URL')
    if not db_url:
        print("Error: MEMORY_DB_URL environment variable not set")
        sys.exit(1)
    
    print(f"Connecting to database...")
    
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Check if pgvector is available
        print("Checking for pgvector extension...")
        cur.execute("SELECT * FROM pg_available_extensions WHERE name = 'vector';")
        result = cur.fetchone()
        
        if not result:
            print("❌ pgvector extension NOT available!")
            print("   Install on the server with:")
            print("   sudo apt install postgresql-14-pgvector")
            print("   sudo systemctl restart postgresql")
            sys.exit(1)
        
        print("✓ pgvector available, enabling...")
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        
        # Create tables
        print("Creating memories table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                agent_id VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                embedding vector(1536),
                memory_type VARCHAR(20) NOT NULL 
                    CHECK (memory_type IN ('episodic', 'semantic', 'procedural')),
                topics TEXT[] DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                event_date DATE,
                expires_at DATE,
                importance FLOAT DEFAULT 0.5 CHECK (importance BETWEEN 0 AND 1),
                stability FLOAT DEFAULT 0.3 CHECK (stability BETWEEN 0 AND 1),
                last_accessed TIMESTAMPTZ DEFAULT NOW(),
                access_count INTEGER DEFAULT 0,
                source_channel VARCHAR(50),
                source_session VARCHAR(100),
                is_summary BOOLEAN DEFAULT FALSE,
                summarizes UUID[] DEFAULT '{}',
                is_deleted BOOLEAN DEFAULT FALSE
            );
        """)
        print("✓ memories table created")
        
        print("Creating memory_links table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS memory_links (
                source_id UUID REFERENCES memories(id) ON DELETE CASCADE,
                target_id UUID REFERENCES memories(id) ON DELETE CASCADE,
                strength FLOAT DEFAULT 0.5 CHECK (strength BETWEEN 0 AND 1),
                link_type VARCHAR(20) DEFAULT 'association',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                PRIMARY KEY (source_id, target_id)
            );
        """)
        print("✓ memory_links table created")
        
        # Create indexes
        print("Creating indexes...")
        indexes = [
            ("memories_agent_idx", "CREATE INDEX IF NOT EXISTS memories_agent_idx ON memories(agent_id);"),
            ("memories_type_idx", "CREATE INDEX IF NOT EXISTS memories_type_idx ON memories(memory_type);"),
            ("memories_topics_idx", "CREATE INDEX IF NOT EXISTS memories_topics_idx ON memories USING GIN(topics);"),
            ("memories_created_idx", "CREATE INDEX IF NOT EXISTS memories_created_idx ON memories(created_at DESC);"),
            ("memories_active_idx", "CREATE INDEX IF NOT EXISTS memories_active_idx ON memories(agent_id, is_deleted) WHERE is_deleted = FALSE;"),
            ("memory_links_source_idx", "CREATE INDEX IF NOT EXISTS memory_links_source_idx ON memory_links(source_id);"),
            ("memory_links_target_idx", "CREATE INDEX IF NOT EXISTS memory_links_target_idx ON memory_links(target_id);"),
        ]
        for name, stmt in indexes:
            cur.execute(stmt)
            print(f"  ✓ {name}")
        
        # Vector index (only useful with enough data)
        print("Creating vector index...")
        try:
            cur.execute("""
                CREATE INDEX IF NOT EXISTS memories_embedding_idx ON memories 
                USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
            """)
            print("  ✓ memories_embedding_idx")
        except Exception as e:
            print(f"  ⚠ Vector index skipped (will be created when more data exists): {e}")
        
        # Create functions
        print("Creating functions...")
        
        # calculate_retention function
        cur.execute("""
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
                decay_constant := p_stability * importance_boost * 30.0;
                
                IF decay_constant < 1 THEN
                    decay_constant := 1;
                END IF;
                
                RETURN GREATEST(0, LEAST(1, EXP(-days_elapsed / decay_constant)));
            END;
            $$ LANGUAGE plpgsql IMMUTABLE;
        """)
        print("  ✓ calculate_retention")
        
        # reinforce_memory function
        cur.execute("""
            CREATE OR REPLACE FUNCTION reinforce_memory(
                p_memory_id UUID
            ) RETURNS VOID AS $$
            DECLARE
                days_since_access FLOAT;
                spacing_bonus FLOAT;
                current_stability FLOAT;
            BEGIN
                SELECT 
                    stability,
                    EXTRACT(EPOCH FROM (NOW() - last_accessed)) / 86400.0
                INTO current_stability, days_since_access
                FROM memories 
                WHERE id = p_memory_id;
                
                spacing_bonus := LEAST(2.0, days_since_access / 7.0);
                
                UPDATE memories SET
                    last_accessed = NOW(),
                    access_count = access_count + 1,
                    stability = LEAST(1.0, current_stability + 0.1 * spacing_bonus)
                WHERE id = p_memory_id;
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("  ✓ reinforce_memory")
        
        # strengthen_link function
        cur.execute("""
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
                    
                INSERT INTO memory_links (source_id, target_id, strength)
                VALUES (p_target_id, p_source_id, 0.5)
                ON CONFLICT (source_id, target_id) DO UPDATE SET
                    strength = LEAST(1.0, memory_links.strength + p_increment),
                    updated_at = NOW();
            END;
            $$ LANGUAGE plpgsql;
        """)
        print("  ✓ strengthen_link")
        
        # Create view
        print("Creating active_memories view...")
        cur.execute("""
            CREATE OR REPLACE VIEW active_memories AS
            SELECT 
                *,
                calculate_retention(stability, importance, last_accessed) as retention
            FROM memories
            WHERE is_deleted = FALSE;
        """)
        print("  ✓ active_memories view")
        
        # Verify
        print("\n" + "="*50)
        print("VERIFICATION")
        print("="*50)
        
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('memories', 'memory_links');
        """)
        tables = [r[0] for r in cur.fetchall()]
        print(f"Tables: {tables}")
        
        cur.execute("""
            SELECT routine_name FROM information_schema.routines 
            WHERE routine_schema = 'public' 
            AND routine_name IN ('calculate_retention', 'reinforce_memory', 'strengthen_link');
        """)
        functions = [r[0] for r in cur.fetchall()]
        print(f"Functions: {functions}")
        
        print("\n✅ Schema setup complete!")
        
        cur.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
