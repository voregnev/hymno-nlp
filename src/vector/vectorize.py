"""
src/vector/vectorize.py
Векторизация текстов через BGE-M3 и загрузка в Qdrant.
Поддерживает dense + sparse (hybrid search).
"""
import logging
import argparse
import psycopg
from psycopg.rows import dict_row
from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct,
    SparseVectorParams, SparseIndexParams,
    SparseVector,
)
from dotenv import load_dotenv
import os

load_dotenv()
log = logging.getLogger(__name__)

try:
    from sentence_transformers import SentenceTransformer
    _st_available = True
except ImportError:
    _st_available = False
    log.warning("sentence-transformers not installed")


COLLECTION_CONFIG = {
    "hymns_cu":          ("cu",  "hymns_cu"),
    "hymns_grc":         ("grc", "hymns_grc"),
    "hymns_multilingual":("all", "hymns_multilingual"),
}

FETCH_UNITS = """
SELECT id::text, full_text, lang, genre, glas,
       office, section, ode_number, unit_type,
       menaion_month, menaion_day, pascha_offset,
       author, is_doxasticon, is_theotokion,
       left(full_text, 100) AS incipit
FROM text_units
WHERE lang = ANY(%s)
ORDER BY lang, id
"""


def ensure_collection(client: QdrantClient, name: str, dim: int = 1024):
    existing = {c.name for c in client.get_collections().collections}
    if name not in existing:
        client.create_collection(
            collection_name=name,
            vectors_config={"dense": VectorParams(size=dim, distance=Distance.COSINE)},
            sparse_vectors_config={
                "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False))
            },
        )
        log.info(f"Created collection: {name}")
    else:
        log.info(f"Collection exists: {name}")


def build_payload(row: dict) -> dict:
    p = {
        "lang":        row["lang"],
        "genre":       row["genre"],
        "glas":        row["glas"],
        "office":      row["office"],
        "section":     row["section"],
        "unit_type":   row["unit_type"],
        "incipit":     row["incipit"],
        "author":      row["author"],
        "is_doxasticon": row["is_doxasticon"],
        "is_theotokion": row["is_theotokion"],
    }
    if row.get("menaion_month"):
        p["menaion_month"] = row["menaion_month"]
        p["menaion_day"]   = row["menaion_day"]
    if row.get("pascha_offset") is not None:
        p["pascha_offset"] = row["pascha_offset"]
    return {k: v for k, v in p.items() if v is not None}


def vectorize_and_load(
    pg_dsn: str,
    qdrant_client: QdrantClient,
    langs: list[str],
    collection_name: str,
    model_name: str = "BAAI/bge-m3",
    batch_size: int = 32,
):
    if not _st_available:
        log.error("sentence-transformers required for vectorization")
        return

    log.info(f"Loading model: {model_name}")
    model = SentenceTransformer(model_name)

    ensure_collection(qdrant_client, collection_name)

    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(FETCH_UNITS, [langs])
            rows = cur.fetchall()

    log.info(f"Vectorizing {len(rows)} units → {collection_name}")

    for batch_start in range(0, len(rows), batch_size):
        batch = rows[batch_start:batch_start + batch_size]
        texts = [r["full_text"] for r in batch]

        # Dense embeddings
        dense_vecs = model.encode(
            texts, batch_size=batch_size,
            normalize_embeddings=True, show_progress_bar=False,
        )

        points = []
        for i, row in enumerate(batch):
            payload = build_payload(row)
            points.append(PointStruct(
                id=row["id"],
                vector={"dense": dense_vecs[i].tolist()},
                payload=payload,
            ))

        qdrant_client.upsert(collection_name=collection_name, points=points)

        if (batch_start // batch_size) % 10 == 0:
            log.info(f"  {batch_start + len(batch)}/{len(rows)}")

    log.info(f"Done: {collection_name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn",       default=os.getenv("PG_DSN"))
    parser.add_argument("--qdrant-host", default=os.getenv("QDRANT_HOST", "localhost"))
    parser.add_argument("--qdrant-port", type=int, default=int(os.getenv("QDRANT_PORT", "6333")))
    parser.add_argument("--model",     default="BAAI/bge-m3")
    parser.add_argument("--batch-size",type=int, default=32)
    parser.add_argument("--collection",default="hymns_multilingual",
                        choices=list(COLLECTION_CONFIG))
    args = parser.parse_args()

    client = QdrantClient(host=args.qdrant_host, port=args.qdrant_port)

    lang_filter, coll_name = COLLECTION_CONFIG[args.collection]
    langs = ["cu", "grc", "ru"] if lang_filter == "all" else [lang_filter]

    vectorize_and_load(
        pg_dsn=args.dsn,
        qdrant_client=client,
        langs=langs,
        collection_name=coll_name,
        model_name=args.model,
        batch_size=args.batch_size,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
