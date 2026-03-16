"""
src/graph/build_graph.py
Строит граф Neo4j из данных PostgreSQL.
TextUnit узлы + структурные связи: IN_SECTION, IN_TONE, PRECEDES.
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

MERGE_UNIT = """
MERGE (tu:TextUnit {id: $id})
SET tu.incipit       = $incipit,
    tu.lang          = $lang,
    tu.genre         = $genre,
    tu.source_ref    = $source_ref,
    tu.position_key  = $position_key
"""

LINK_GLAS = """
MATCH (tu:TextUnit {id: $id})
MERGE (g:Glas {value: $glas})
MERGE (tu)-[:IN_TONE]->(g)
"""

LINK_SECTION = """
MATCH (tu:TextUnit {id: $id})
MERGE (sec:Section {key: $section_key})
SET sec.name    = $section,
    sec.office  = $office,
    sec.book    = $book
MERGE (tu)-[:IN_SECTION {order: $order}]->(sec)
"""

LINK_ODE = """
MATCH (tu:TextUnit {id: $id})
MERGE (sec:Section {key: $section_key})
MERGE (ode:Ode {key: $ode_key})
SET ode.number      = $ode_number,
    ode.section_key = $section_key
MERGE (sec)-[:HAS_ODE]->(ode)
MERGE (tu)-[:IN_ODE {order: $order, unit_type: $unit_type}]->(ode)
"""

LINK_AUTHOR = """
MATCH (tu:TextUnit {id: $id})
MERGE (a:Author {name: $author})
MERGE (tu)-[:AUTHORED_BY {confidence: $confidence}]->(a)
"""

LINK_PODOBEN = """
MATCH (tu:TextUnit {id: $id})
MERGE (p:Podoben {incipit_cu: $podoben})
MERGE (tu)-[:MODELS_ON]->(p)
"""

BUILD_PRECEDES = """
MATCH (a:TextUnit)-[r1:IN_SECTION]->(sec:Section)<-[r2:IN_SECTION]-(b:TextUnit)
WHERE r1.order + 1 = r2.order
  AND a.lang = b.lang
MERGE (a)-[:PRECEDES]->(b)
"""

BUILD_PRECEDES_ODE = """
MATCH (a:TextUnit)-[r1:IN_ODE]->(ode:Ode)<-[r2:IN_ODE]-(b:TextUnit)
WHERE r1.order + 1 = r2.order
  AND a.lang = b.lang
MERGE (a)-[:PRECEDES]->(b)
"""


def load_units_from_pg(dsn: str, lang_filter: list[str] | None = None) -> list[dict]:
    query = """
        SELECT id, source_ref, lang, book,
               left(full_text, 100) AS incipit,
               genre, author, author_confidence, podoben,
               office, section, ode_number, unit_type,
               section_order, glas
        FROM text_units
    """
    params = []
    if lang_filter:
        query += " WHERE lang = ANY(%s)"
        params.append(lang_filter)
    query += " ORDER BY book, lang, glas, section, section_order"

    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(query, params or None)
            return cur.fetchall()


def build_graph(units: list[dict], neo4j_driver, batch_size: int = 100):
    total = len(units)
    log.info(f"Building graph for {total} units...")

    with neo4j_driver.session() as session:
        for i, u in enumerate(units):
            if i % 200 == 0:
                log.info(f"  {i}/{total}")

            position_key = (
                f"{u['book']}/{u['office'] or '?'}/{u['section'] or '?'}/"
                f"g{u['glas'] or 0}/d0/{u['unit_type'] or 'unk'}{u['section_order']:03d}"
            )

            # Создаём/обновляем узел
            session.run(MERGE_UNIT, {
                "id": str(u["id"]), "incipit": u["incipit"],
                "lang": u["lang"], "genre": u["genre"],
                "source_ref": u["source_ref"], "position_key": position_key,
            })

            # Глас
            if u.get("glas"):
                session.run(LINK_GLAS, {"id": str(u["id"]), "glas": u["glas"]})

            # Секция или ода
            section_key = f"{u['book']}.{u['office']}.{u['section']}"
            if u["section"] == "canon" and u.get("ode_number"):
                ode_key = f"{section_key}.ode{u['ode_number']}"
                session.run(LINK_ODE, {
                    "id": str(u["id"]),
                    "section_key": section_key,
                    "ode_key": ode_key,
                    "ode_number": u["ode_number"],
                    "order": u["section_order"],
                    "unit_type": u["unit_type"] or "troparion",
                })
            elif u.get("section"):
                session.run(LINK_SECTION, {
                    "id": str(u["id"]),
                    "section_key": section_key,
                    "section": u["section"],
                    "office": u["office"] or "",
                    "book": u["book"],
                    "order": u["section_order"],
                })

            # Автор
            if u.get("author"):
                session.run(LINK_AUTHOR, {
                    "id": str(u["id"]),
                    "author": u["author"],
                    "confidence": u.get("author_confidence", "low"),
                })

            # Подобен
            if u.get("podoben"):
                session.run(LINK_PODOBEN, {
                    "id": str(u["id"]),
                    "podoben": u["podoben"],
                })

        # Строим PRECEDES рёбра
        log.info("Building PRECEDES edges...")
        session.run(BUILD_PRECEDES)
        session.run(BUILD_PRECEDES_ODE)

    log.info("Graph build complete")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default=os.getenv("PG_DSN"))
    parser.add_argument("--neo4j-uri",  default=os.getenv("NEO4J_URI",  "bolt://localhost:7687"))
    parser.add_argument("--neo4j-user", default=os.getenv("NEO4J_USER", "neo4j"))
    parser.add_argument("--neo4j-pass", default=os.getenv("NEO4J_PASSWORD", "hymn1234"))
    parser.add_argument("--lang", nargs="+", help="Filter by language(s): cu grc ru")
    args = parser.parse_args()

    driver = GraphDatabase.driver(
        args.neo4j_uri,
        auth=(args.neo4j_user, args.neo4j_pass),
    )
    try:
        units = load_units_from_pg(args.dsn, args.lang)
        build_graph(units, driver)
    finally:
        driver.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
