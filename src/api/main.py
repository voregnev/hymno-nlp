"""
src/api/main.py
FastAPI приложение — REST эндпоинты для поиска и навигации.
"""
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(
    title="Hymnography NLP API",
    description="Сравнительный анализ гимнографических текстов",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic models ─────────────────────────────────────────────────────────

class TextUnitOut(BaseModel):
    id: str
    lang: str
    incipit: str
    full_text: Optional[str] = None
    genre: Optional[str] = None
    glas: Optional[int] = None
    office: Optional[str] = None
    section: Optional[str] = None
    author: Optional[str] = None
    position_key: Optional[str] = None


class SearchResult(BaseModel):
    id: str
    incipit: str
    lang: str
    genre: Optional[str]
    glas: Optional[int]
    score: float
    parallel_id: Optional[str] = None
    parallel_incipit: Optional[str] = None


class CompareResult(BaseModel):
    unit_a: TextUnitOut
    unit_b: TextUnitOut
    similarity: Optional[float] = None
    strophes_a: list[str] = []
    strophes_b: list[str] = []


# ─── DB connections (lazy init) ──────────────────────────────────────────────

_pg_pool = None
_neo4j_driver = None
_qdrant_client = None


async def get_pg():
    global _pg_pool
    if _pg_pool is None:
        import psycopg_pool
        _pg_pool = psycopg_pool.AsyncConnectionPool(
            os.getenv("PG_DSN", "postgresql://hymn:hymn@localhost:5432/hymnography"),
            min_size=2, max_size=10,
        )
    return _pg_pool


def get_neo4j():
    global _neo4j_driver
    if _neo4j_driver is None:
        from neo4j import AsyncGraphDatabase
        _neo4j_driver = AsyncGraphDatabase.driver(
            os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            auth=(os.getenv("NEO4J_USER", "neo4j"),
                  os.getenv("NEO4J_PASSWORD", "hymn1234")),
        )
    return _neo4j_driver


def get_qdrant():
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        _qdrant_client = QdrantClient(
            host=os.getenv("QDRANT_HOST", "localhost"),
            port=int(os.getenv("QDRANT_PORT", "6333")),
        )
    return _qdrant_client


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/text/{unit_id}", response_model=TextUnitOut)
async def get_text(unit_id: str, include_full: bool = False):
    """Получить текстовую единицу по ID."""
    pool = await get_pg()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            fields = "id::text, lang, left(full_text,100) AS incipit, genre, glas, office, section, author"
            if include_full:
                fields += ", full_text"
            await cur.execute(
                f"SELECT {fields} FROM text_units WHERE id = %s",
                [unit_id],
            )
            row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Text unit not found")
    return TextUnitOut(**dict(zip([d[0] for d in cur.description], row)))


@app.get("/text/{unit_id}/strophes")
async def get_strophes(unit_id: str):
    """Получить строфы текстовой единицы."""
    pool = await get_pg()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT position, text FROM strophes WHERE unit_id = %s ORDER BY position",
                [unit_id],
            )
            rows = await cur.fetchall()
    return [{"position": r[0], "text": r[1]} for r in rows]


@app.get("/text/{unit_id}/parallel")
async def get_parallel(unit_id: str):
    """Получить параллельный текст на другом языке через Neo4j."""
    driver = get_neo4j()
    async with driver.session() as session:
        result = await session.run(
            """
            MATCH (a:TextUnit {id: $id})-[r:HAS_PARALLEL]->(b:TextUnit)
            RETURN b.id AS parallel_id, r.similarity AS sim, b.lang AS lang
            ORDER BY r.similarity DESC LIMIT 5
            """,
            id=unit_id,
        )
        records = await result.data()
    return records


@app.get("/compare", response_model=CompareResult)
async def compare(id_a: str, id_b: str):
    """Сравнить две текстовые единицы side-by-side."""
    pool = await get_pg()
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """SELECT id::text, lang, full_text,
                          left(full_text,100) AS incipit,
                          genre, glas, office, section, author
                   FROM text_units WHERE id = ANY(%s)""",
                [[id_a, id_b]],
            )
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

            # Строфы
            await cur.execute(
                "SELECT unit_id::text, position, text FROM strophes "
                "WHERE unit_id = ANY(%s) ORDER BY unit_id, position",
                [[id_a, id_b]],
            )
            strophe_rows = await cur.fetchall()

    units = {r[0]: dict(zip(cols, r)) for r in rows}
    if id_a not in units or id_b not in units:
        raise HTTPException(404, "One or both units not found")

    strophes_by_unit: dict[str, list] = {id_a: [], id_b: []}
    for uid, pos, text in strophe_rows:
        if uid in strophes_by_unit:
            strophes_by_unit[uid].append(text)

    # Similarity из Neo4j
    sim = None
    driver = get_neo4j()
    async with driver.session() as session:
        r = await session.run(
            "MATCH (a:TextUnit {id:$a})-[rel:HAS_PARALLEL]->(b:TextUnit {id:$b}) "
            "RETURN rel.similarity AS sim",
            a=id_a, b=id_b,
        )
        rec = await r.single()
        if rec:
            sim = rec["sim"]

    return CompareResult(
        unit_a=TextUnitOut(**units[id_a]),
        unit_b=TextUnitOut(**units[id_b]),
        similarity=sim,
        strophes_a=strophes_by_unit[id_a],
        strophes_b=strophes_by_unit[id_b],
    )


@app.get("/search", response_model=list[SearchResult])
async def search(
    q: str = Query(..., min_length=2),
    lang: Optional[str] = None,
    glas: Optional[int] = None,
    genre: Optional[str] = None,
    limit: int = Query(10, le=50),
    semantic: bool = True,
):
    """Гибридный поиск: BM25 + векторный (если semantic=True)."""
    pool = await get_pg()
    results = []

    # Full-text поиск через PostgreSQL tsvector
    conditions = ["search_vec @@ plainto_tsquery('russian', %s)"]
    params: list = [q]
    if lang:
        conditions.append("lang = %s")
        params.append(lang)
    if glas:
        conditions.append("glas = %s")
        params.append(glas)
    if genre:
        conditions.append("genre = %s")
        params.append(genre)

    where = " AND ".join(conditions)
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""SELECT id::text, left(full_text,100) AS incipit,
                          lang, genre, glas,
                          ts_rank(search_vec, plainto_tsquery('russian', %s)) AS score
                   FROM text_units
                   WHERE {where}
                   ORDER BY score DESC
                   LIMIT %s""",
                [q] + params + [limit],
            )
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

    for row in rows:
        d = dict(zip(cols, row))
        results.append(SearchResult(**d))

    # Векторный поиск через Qdrant (дополнительно)
    if semantic and results:
        # TODO: добавить BGE-M3 эмбеддинг запроса + Qdrant ANN
        # Пока возвращаем только full-text результаты
        pass

    return results


@app.get("/navigate/section")
async def navigate_section(
    book: str, office: str, section: str,
    glas: Optional[int] = None, lang: str = "cu",
):
    """Получить все тексты раздела службы по порядку."""
    pool = await get_pg()
    conditions = [
        "book = %s", "office = %s", "section = %s", "lang = %s"
    ]
    params: list = [book, office, section, lang]
    if glas:
        conditions.append("glas = %s")
        params.append(glas)

    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                f"""SELECT id::text, left(full_text,100) AS incipit,
                          genre, unit_type, ode_number, section_order,
                          is_doxasticon, is_theotokion
                   FROM text_units
                   WHERE {' AND '.join(conditions)}
                   ORDER BY ode_number NULLS FIRST, section_order""",
                params,
            )
            rows = await cur.fetchall()
            cols = [d[0] for d in cur.description]

    return [dict(zip(cols, r)) for r in rows]
