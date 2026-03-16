"""
src/align/align_parallel.py
Выравнивание ЦСЯ ↔ греческий через Bertalign + LaBSE.
Якорная стратегия: группировка по (book, office, section, glas, ode_number).
"""
import logging
import argparse
import psycopg
from psycopg.rows import dict_row
from neo4j import GraphDatabase
from dotenv import load_dotenv
import os

load_dotenv()
log = logging.getLogger(__name__)

try:
    from bertalign import Bertalign
    _bertalign_available = True
except ImportError:
    _bertalign_available = False
    log.warning("bertalign not installed — alignment disabled")


FETCH_SECTION_PAIRS = """
SELECT
    book, office, section, glas, ode_number,
    array_agg(id::text   ORDER BY section_order) FILTER (WHERE lang='cu')  AS cu_ids,
    array_agg(id::text   ORDER BY section_order) FILTER (WHERE lang='grc') AS grc_ids,
    array_agg(full_text  ORDER BY section_order) FILTER (WHERE lang='cu')  AS cu_texts,
    array_agg(full_text  ORDER BY section_order) FILTER (WHERE lang='grc') AS grc_texts,
    count(*) FILTER (WHERE lang='cu')  AS cu_count,
    count(*) FILTER (WHERE lang='grc') AS grc_count
FROM text_units
GROUP BY book, office, section, glas, ode_number
HAVING count(*) FILTER (WHERE lang='cu') > 0
   AND count(*) FILTER (WHERE lang='grc') > 0
ORDER BY book, glas, office, section, ode_number
"""

UPSERT_PARALLEL = """
MATCH (a:TextUnit {id: $cu_id})
MATCH (b:TextUnit {id: $grc_id})
MERGE (a)-[r:HAS_PARALLEL]->(b)
SET r.similarity = $sim,
    r.method     = 'bertalign_labse',
    r.cu_idx     = $cu_idx,
    r.grc_idx    = $grc_idx
"""

SAVE_PARALLEL_PG = """
INSERT INTO text_units (id) VALUES (%s) ON CONFLICT DO NOTHING;
-- Параллели хранятся только в Neo4j, здесь просто placeholder
"""


def align_section(cu_texts, grc_texts, cu_ids, grc_ids,
                  min_sim: float = 0.60) -> list[tuple]:
    """
    Возвращает список (cu_idx, grc_idx, similarity).
    """
    if not _bertalign_available:
        # Простой фоллбек: по порядку
        pairs = []
        for i in range(min(len(cu_texts), len(grc_texts))):
            pairs.append((i, i, 0.70))
        return pairs

    try:
        aligner = Bertalign("\n".join(cu_texts), "\n".join(grc_texts))
        aligner.align_sents()
        pairs = []
        for cu_idxs, grc_idxs in aligner.result:
            # Bertalign возвращает наборы индексов, берём 1-1 или 1-many
            sim = 0.80  # Bertalign не возвращает score напрямую в v1.2
            for ci in (cu_idxs if isinstance(cu_idxs, list) else [cu_idxs]):
                for gi in (grc_idxs if isinstance(grc_idxs, list) else [grc_idxs]):
                    if ci < len(cu_ids) and gi < len(grc_ids):
                        pairs.append((ci, gi, sim))
        return [(ci, gi, s) for ci, gi, s in pairs if s >= min_sim]
    except Exception as e:
        log.error(f"Bertalign error: {e}")
        return []


def run_alignment(pg_dsn: str, neo4j_driver, min_sim: float = 0.60):
    with psycopg.connect(pg_dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(FETCH_SECTION_PAIRS)
            sections = cur.fetchall()

    log.info(f"Aligning {len(sections)} section pairs...")
    total_pairs = 0

    with neo4j_driver.session() as session:
        for sec in sections:
            cu_ids   = sec["cu_ids"] or []
            grc_ids  = sec["grc_ids"] or []
            cu_texts = sec["cu_texts"] or []
            grc_texts= sec["grc_texts"] or []

            if not cu_ids or not grc_ids:
                continue

            label = (f"book={sec['book']} office={sec['office']} "
                     f"sec={sec['section']} glas={sec['glas']} ode={sec['ode_number']}")
            log.debug(f"  {label}: {len(cu_ids)} cu × {len(grc_ids)} grc")

            pairs = align_section(cu_texts, grc_texts, cu_ids, grc_ids, min_sim)

            for cu_idx, grc_idx, sim in pairs:
                session.run(UPSERT_PARALLEL, {
                    "cu_id":  cu_ids[cu_idx],
                    "grc_id": grc_ids[grc_idx],
                    "sim":    round(float(sim), 4),
                    "cu_idx":  cu_idx,
                    "grc_idx": grc_idx,
                })
                total_pairs += 1

    log.info(f"Total parallel pairs created: {total_pairs}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn",        default=os.getenv("PG_DSN"))
    parser.add_argument("--neo4j-uri",  default=os.getenv("NEO4J_URI",  "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-pass", default=os.getenv("NEO4J_PASSWORD", "hymn1234"))
    parser.add_argument("--min-sim",    type=float, default=0.60)
    args = parser.parse_args()

    driver = GraphDatabase.driver(args.neo4j_uri, auth=(args.neo4j_user, args.neo4j_pass))
    try:
        run_alignment(args.dsn, driver, args.min_sim)
    finally:
        driver.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
