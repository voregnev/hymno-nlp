"""
scripts/check_connections.py
Проверяет подключения ко всем сервисам перед запуском пайплайна.
"""
import sys
from dotenv import load_dotenv
import os

load_dotenv()

def check_postgres():
    try:
        import psycopg
        dsn = os.getenv("PG_DSN", "postgresql://hymn:hymn@localhost:5432/hymnography")
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) FROM text_units")
                count = cur.fetchone()[0]
        print(f"  PostgreSQL OK — text_units: {count} rows")
        return True
    except Exception as e:
        print(f"  PostgreSQL FAIL: {e}")
        return False


def check_neo4j():
    try:
        from neo4j import GraphDatabase
        uri  = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
        user = os.getenv("NEO4J_USER",     "neo4j")
        pw   = os.getenv("NEO4J_PASSWORD", "hymn1234")
        with GraphDatabase.driver(uri, auth=(user, pw)) as d:
            with d.session() as s:
                r = s.run("MATCH (n:TextUnit) RETURN count(n) AS c")
                count = r.single()["c"]
        print(f"  Neo4j OK — TextUnit nodes: {count}")
        return True
    except Exception as e:
        print(f"  Neo4j FAIL: {e}")
        return False


def check_qdrant():
    try:
        from qdrant_client import QdrantClient
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        client = QdrantClient(host=host, port=port)
        colls = [c.name for c in client.get_collections().collections]
        print(f"  Qdrant OK — collections: {colls or '(none yet)'}")
        return True
    except Exception as e:
        print(f"  Qdrant FAIL: {e}")
        return False


def check_anthropic():
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if key and key.startswith("sk-ant-"):
        print(f"  Anthropic key OK (***{key[-4:]})")
        return True
    elif not key:
        print("  Anthropic key NOT SET — LLM fallback disabled")
        return True  # не критично
    else:
        print("  Anthropic key looks wrong")
        return False


if __name__ == "__main__":
    print("Checking connections...\n")
    results = {
        "PostgreSQL": check_postgres(),
        "Neo4j":      check_neo4j(),
        "Qdrant":     check_qdrant(),
        "Anthropic":  check_anthropic(),
    }
    print()
    failed = [k for k, v in results.items() if not v]
    if failed:
        print(f"FAILED: {failed}")
        print("Run: docker compose up -d")
        sys.exit(1)
    else:
        print("All connections OK. Ready to run pipeline.")
