#!/usr/bin/env python3
"""Setup the cognitive memory database schema."""

import os
import sys

try:
    import psycopg2
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
            print("⚠ pgvector extension not available. You may need to install it on the server.")
            print("  For managed Postgres: Check if your provider supports pgvector")
            print("  For self-hosted: apt install postgresql-14-pgvector")
        else:
            print("✓ pgvector available")
        
        # Read and execute schema
        script_dir = os.path.dirname(os.path.abspath(__file__))
        schema_path = os.path.join(script_dir, '..', 'schema.sql')
        
        print(f"Running schema from {schema_path}...")
        with open(schema_path, 'r') as f:
            schema = f.read()
        
        # Split by statements and execute each
        statements = schema.split(';')
        for stmt in statements:
            stmt = stmt.strip()
            if stmt and not stmt.startswith('--'):
                try:
                    cur.execute(stmt)
                    print(f"  ✓ Executed: {stmt[:60]}...")
                except psycopg2.Error as e:
                    if 'already exists' in str(e):
                        print(f"  - Skipped (exists): {stmt[:60]}...")
                    else:
                        print(f"  ⚠ Warning: {e}")
        
        # Verify tables exist
        print("\nVerifying tables...")
        cur.execute("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name IN ('memories', 'memory_links');
        """)
        tables = [r[0] for r in cur.fetchall()]
        print(f"  Tables: {tables}")
        
        # Verify functions exist
        cur.execute("""
            SELECT routine_name FROM information_schema.routines 
            WHERE routine_schema = 'public' AND routine_name IN ('calculate_retention', 'reinforce_memory', 'strengthen_link');
        """)
        functions = [r[0] for r in cur.fetchall()]
        print(f"  Functions: {functions}")
        
        print("\n✓ Schema setup complete!")
        
        cur.close()
        conn.close()
        
    except psycopg2.Error as e:
        print(f"Database error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
