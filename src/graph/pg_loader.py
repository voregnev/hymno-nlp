"""
src/graph/pg_loader.py
Загрузка ParsedUnit объектов в PostgreSQL.
"""
import json
import logging
import pathlib
import argparse
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
import os

load_dotenv()
log = logging.getLogger(__name__)

INSERT_UNIT = """
INSERT INTO text_units (
    id, source_ref, lang, book,
    office, section, ode_number, unit_type, section_order,
    glas, day_of_week, menaion_month, menaion_day, pascha_offset,
    full_text, genre, author, author_confidence,
    podoben, acrostic, translation_type,
    is_doxasticon, is_theotokion, theotokion_source,
    parse_method, needs_review
) VALUES (
    %(id)s, %(source_ref)s, %(lang)s, %(book)s,
    %(office)s, %(section)s, %(ode_number)s, %(unit_type)s, %(section_order)s,
    %(glas)s, %(day_of_week)s, %(menaion_month)s, %(menaion_day)s, %(pascha_offset)s,
    %(full_text)s, %(genre)s, %(author)s, %(author_confidence)s,
    %(podoben)s, %(acrostic)s, %(translation_type)s,
    %(is_doxasticon)s, %(is_theotokion)s, %(theotokion_source)s,
    %(parse_method)s, %(needs_review)s
)
ON CONFLICT (source_ref) DO UPDATE SET
    full_text         = EXCLUDED.full_text,
    genre             = EXCLUDED.genre,
    author            = EXCLUDED.author,
    glas              = EXCLUDED.glas,
    parse_method      = EXCLUDED.parse_method,
    needs_review      = EXCLUDED.needs_review,
    updated_at        = NOW()
RETURNING id;
"""

INSERT_STROPHE = """
INSERT INTO strophes (unit_id, position, text)
VALUES (%s, %s, %s)
ON CONFLICT (unit_id, position) DO NOTHING;
"""


def jsonl_to_pg(jsonl_path: pathlib.Path, dsn: str, batch_size: int = 200):
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        total = 0
        with jsonl_path.open(encoding="utf-8") as f:
            batch_units = []
            batch_strophes = []

            for line in f:
                d = json.loads(line)
                pos = d.get("position", {})

                row = {
                    "id":               d["id"],
                    "source_ref":       d["source_ref"],
                    "lang":             d["lang"],
                    "book":             pos.get("book", "unknown"),
                    "office":           pos.get("office"),
                    "section":          pos.get("section"),
                    "ode_number":       pos.get("ode_number"),
                    "unit_type":        pos.get("unit_type"),
                    "section_order":    pos.get("section_order", 0),
                    "glas":             pos.get("glas"),
                    "day_of_week":      pos.get("day_of_week"),
                    "menaion_month":    pos.get("menaion_month"),
                    "menaion_day":      pos.get("menaion_day"),
                    "pascha_offset":    pos.get("pascha_offset"),
                    "full_text":        d["raw_text"],
                    "genre":            d.get("genre"),
                    "author":           d.get("author"),
                    "author_confidence":d.get("author_confidence", "low"),
                    "podoben":          d.get("podoben"),
                    "acrostic":         d.get("acrostic"),
                    "translation_type": d.get("translation_type"),
                    "is_doxasticon":    d.get("is_doxasticon", False),
                    "is_theotokion":    d.get("is_theotokion", False),
                    "theotokion_source":d.get("theotokion_source"),
                    "parse_method":     json.dumps(d.get("parse_method", {})),
                    "needs_review":     d.get("needs_review", False),
                }
                batch_units.append(row)

                # Строфы
                for i, text in enumerate(d.get("strophes", [])):
                    batch_strophes.append((d["id"], i, text))

                if len(batch_units) >= batch_size:
                    _flush(conn, batch_units, batch_strophes)
                    total += len(batch_units)
                    log.info(f"  Inserted {total} units...")
                    batch_units.clear()
                    batch_strophes.clear()

            if batch_units:
                _flush(conn, batch_units, batch_strophes)
                total += len(batch_units)

    log.info(f"Total: {total} units loaded from {jsonl_path.name}")


def _flush(conn, units, strophes):
    with conn.cursor() as cur:
        for row in units:
            cur.execute(INSERT_UNIT, row)
        if strophes:
            cur.executemany(INSERT_STROPHE, strophes)
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True,
                        help="JSONL files from parser output")
    parser.add_argument("--dsn", default=os.getenv("PG_DSN",
                        "postgresql://hymn:hymn@localhost:5432/hymnography"))
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    for path_str in args.input:
        p = pathlib.Path(path_str)
        log.info(f"Loading {p} → PostgreSQL")
        jsonl_to_pg(p, args.dsn, args.batch_size)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
