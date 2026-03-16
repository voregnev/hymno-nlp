# Архитектура системы

## Три хранилища и их роли

### Neo4j — граф литургических связей
Хранит структуру и связи. **Не хранит `full_text`.**

**Узлы:**
- `:TextUnit` — атомарная единица (тропарь, ирмос, стихира и т.д.)
- `:Glas` — глас 1–8
- `:Section` — раздел службы (lihc, aposticha, canon, ...)
- `:Ode` — песнь канона 1–9
- `:Office` — суточный круг (vespers, matins, ...)
- `:Author` — автор текста
- `:Feast` / `:Saint` — праздник / святой
- `:Podoben` — мелодическая модель
- `:Collection` — книга (Октоих, Минея, Триодь, ...)

**Рёбра:**
```
(TextUnit)-[:IN_TONE]->(Glas)
(TextUnit)-[:IN_SECTION {order}]->(Section)
(TextUnit)-[:IN_ODE {order, unit_type}]->(Ode)
(Ode)-[:IN_SECTION]->(Section)
(Section)-[:IN_OFFICE]->(Office)
(TextUnit)-[:AUTHORED_BY {confidence}]->(Author)
(TextUnit)-[:MODELS_ON]->(Podoben)
(TextUnit)-[:HAS_PARALLEL {similarity, method}]->(TextUnit)  # ЦСЯ ↔ GRC
(TextUnit)-[:PRECEDES]->(TextUnit)  # порядок в секции
(TextUnit)-[:FOR_FEAST]->(Feast)
(TextUnit)-[:IN_COLLECTION]->(Collection)
```

### PostgreSQL 16 — тексты и строфы
**Таблицы:**
- `text_units` — полный текст + все атрибуты + позиция
- `strophes` — строфы (строки) каждой единицы
- `annotations` — экспертные аннотации
- `biblical_refs` — библейские аллюзии

### Qdrant — векторный поиск
**Коллекции:**
- `hymns_cu` — тексты на ЦСЯ, BGE-M3 dense
- `hymns_grc` — тексты на греческом, BGE-M3 dense
- `hymns_multilingual` — все языки, кросс-языковой поиск

**Payload** (для фильтрации без JOIN):
`lang, genre, glas, office, section, incipit, author, is_doxasticon, is_theotokion`

## Общий ключ: `id = PostgreSQL UUID = Neo4j TextUnit.id = Qdrant point id`

## Потоки данных

### Batch (offline)
```
azbyka.ru HTML
  → scraper.py            → data/raw/*.txt
  → parse_pipeline.py     → data/processed/*.jsonl
  → pg_loader.py          → PostgreSQL text_units + strophes
  → build_graph.py        → Neo4j TextUnit + структурные связи
  → align_parallel.py     → Neo4j HAS_PARALLEL рёбра
  → vectorize.py          → Qdrant hymns_* коллекции
```

### Online query (<200ms)
```
User query
  ├── BM25 (Qdrant sparse)        ─┐
  ├── Dense ANN (Qdrant)          ─┤ RRF fusion
  └── Graph traversal (Neo4j)    ─┘
           │
           ▼
    RAG context → LLM → ответ + цитаты
```

## Атомарная единица: `:TextUnit`

Одна неделимая гимнографическая единица:
тропарь / ирмос / стихира / кондак / седален / богородичен / светилен

**Не** слово, **не** стих — это уровень строфы (`:Strophe`).

## Место в богослужении: 5-мерная координата

```python
position_key = "octoechos/matins/canon/g8/d0/ode3/troparion002"
# book / office / section / glas / day_of_week / ode_number / unit_type + order
```

Три независимых цикла:
- **Суточный** — office: vespers_small/great → matins → liturgy
- **Седмичный** — glas (1–8), day_of_week (0–6)
- **Годичный неподвижный** — menaion_month + menaion_day
- **Годичный подвижный** — pascha_offset (дней от Пасхи, -70..+56)
