# MVP — Пошаговый план (12 недель)

## Скоуп

**Корпус:** Октоих глас 8 — ЦСЯ + греческий (~800 текстовых единиц)
**Источник:** azbyka.ru (OCR не нужен — тексты доступны как HTML)

## Критерии готовности (Definition of Done)

| Критерий | Целевое значение | Проверка |
|---|---|---|
| Корпус загружен | ≥ 700 единиц глас 8 (оба языка) | `SELECT count(*) FROM text_units WHERE glas=8` |
| Классификация жанра | F1 ≥ 0.88 на hold-out 20% | `pytest tests/` |
| Выравнивание | Precision ≥ 0.80 на 100 вручную проверенных парах | Экспертная оценка |
| Семантический поиск | Recall@5 ≥ 0.70 на 50 тест-запросах | `scripts/eval_search.py` |
| Граф | Все 700 единиц в Neo4j с базовыми связями | Neo4j Browser |
| UI | Поиск + side-by-side за < 500ms | Ручное тестирование |
| Экспертная оценка | Положительная оценка 2 литургистов | UX-интервью |

## Понедельный план

### Неделя 1–2: Инфраструктура
- `docker compose up -d` — поднять Neo4j + Qdrant + PostgreSQL
- `python scripts/check_connections.py` — проверить подключения
- Настройка DVC + W&B + GitHub Actions
- `.env` из `config/env.example`

### Неделя 2–3: Скрапинг ЦСЯ
```bash
python src/scraper/scrape.py --book oktoih_cu
```
Ожидаемый результат: ~28 файлов `data/raw/oktoih_cu/*.txt`

### Неделя 3–4: Скрапинг греческого
```bash
python src/scraper/scrape.py --book oktoih_grc
```
Ожидаемый результат: ~14 файлов `data/raw/oktoih_grc/*.txt`

### Неделя 4–5: Парсинг
```bash
python src/parser/parse_pipeline.py \
  --input data/raw/oktoih_cu data/raw/oktoih_grc \
  --no-llm  # сначала без LLM
```
Проверить: `pytest tests/test_parser.py -v`
Добавить LLM когда regex покрывает ≥ 80% жанров.

### Неделя 5–6: PostgreSQL
```bash
python src/graph/pg_loader.py \
  --input data/processed/oktoih_cu.jsonl data/processed/oktoih_grc.jsonl
```
Проверить:
```sql
SELECT lang, count(*), count(genre) FROM text_units GROUP BY lang;
```

### Неделя 6–7: Neo4j
```bash
python src/graph/build_graph.py
```
Проверить в Neo4j Browser:
```cypher
MATCH (tu:TextUnit) RETURN count(tu)
MATCH ()-[r:IN_TONE]->() RETURN count(r)
MATCH ()-[r:PRECEDES]->() RETURN count(r)
```

### Неделя 7–8: Выравнивание
```bash
python src/align/align_parallel.py --min-sim 0.60
```
Ручная валидация 100 пар экспертом → пересчёт precision.

### Неделя 8–9: Векторизация
```bash
python src/vector/vectorize.py --collection hymns_cu
python src/vector/vectorize.py --collection hymns_grc
python src/vector/vectorize.py --collection hymns_multilingual
```

### Неделя 9–10: FastAPI
- `/search?q=...&lang=cu&glas=8` — гибридный поиск
- `/text/{id}` — получить текст + строфы
- `/parallel/{id}` — получить параллельный текст
- `/compare?id1=...&id2=...` — сравнение двух текстов

### Неделя 10–11: UI
- React компоненты: SearchBar, TextCard, SideBySideView, DiffViewer
- Интеграция с FastAPI

### Неделя 11–12: Интеграция и тесты
- Интеграционные тесты пайплайна
- UX-интервью с 2 экспертами
- Фикс критических проблем

## Полный пайплайн одной командой

```bash
python src/mlops/pipeline_flow.py
```

## Источники греческого

| Источник | URL | Качество | Статус |
|---|---|---|---|
| azbyka.ru (Παρακλητική 1858) | `/otechnik/greek/oktoih-na-grecheskom-jazyke/{n}` | Хорошее, политонический Unicode | **Основной** |
| azbyka.ru (Μηναίον) | `/otechnik/greek/mineja-{month}-na-grecheskom-jazyke/{n}` | Хорошее | Для Alpha |
| Internet Archive (HOCR) | Παρακλητική (1858) _hocr_searchtext.txt.gz | Низкое (OCR) | Резерв |
| TLG | stephanus.tlg.uci.edu | Академическое | Alpha+ (подписка) |
