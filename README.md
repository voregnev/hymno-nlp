# Hymnography NLP — Система сравнительного анализа гимнографических текстов

Платформа для лингвистического, богословского и литургического анализа гимнографии православного богослужения на **церковнославянском**, **греческом (Byzantine)** и **русском** языках.

## Источники

| Корпус | Язык | URL-паттерн | Объём (MVP) |
|--------|------|-------------|-------------|
| Октоих (ЦСЯ) | cu | `/otechnik/Pravoslavnoe_Bogosluzhenie/oktoih/{n}` | ~28 стр. |
| Октоих (греч.) | grc | `/otechnik/greek/oktoih-na-grecheskom-jazyke/{n}` | ~14 стр. |
| Минея январь (ЦСЯ) | cu | `/otechnik/Pravoslavnoe_Bogosluzhenie/mineya-yanvar/{n}` | ~40 стр. |
| Минея январь (греч.) | grc | `/otechnik/greek/mineja-yanvar-na-grecheskom-jazyke/{n}` | ~40 стр. |

## Стек

```
Neo4j 5        — граф литургических связей
PostgreSQL 16  — полные тексты, строфы, аннотации
Qdrant         — векторный / гибридный поиск (BGE-M3)
FastAPI        — REST API
Prefect        — оркестрация ML-пайплайна
W&B            — эксперимент-трекинг
DVC            — версионирование данных
```

## Быстрый старт

```bash
# 1. Поднять инфраструктуру
cp config/env.example .env
docker compose up -d

# 2. Проверить подключения
python scripts/check_connections.py

# 3. Запустить MVP-пайплайн (Октоих глас 8)
python src/scraper/scrape.py --book oktoih_cu --book oktoih_grc
python src/parser/parse_pipeline.py --input data/raw/oktoih_cu data/raw/oktoih_grc
python src/graph/build_graph.py
python src/align/align_parallel.py
python src/vector/vectorize.py
```

## Структура репозитория

```
hymnography-nlp/
├── docs/                   # Документация и ТЗ
│   ├── TZ_v2.md            # Техническое задание
│   ├── architecture.md     # Архитектура системы
│   ├── data_model.md       # Онтология, граф-схема, атрибуты
│   ├── mvp_plan.md         # Пошаговый план MVP (12 недель)
│   ├── sources_greek.md    # Источники греческого корпуса
│   └── liturgical_cycles.md # Суточный/седмичный/годичный круги
├── src/
│   ├── scraper/            # Парсинг azbyka.ru
│   ├── parser/             # Rule-based + LLM извлечение атрибутов
│   ├── graph/              # Neo4j импорт
│   ├── vector/             # Эмбеддинги + Qdrant
│   ├── align/              # Bertalign ЦСЯ ↔ греч.
│   └── mlops/              # Prefect flows, W&B логирование
├── config/                 # Конфиги, env-шаблоны
├── data/
│   ├── raw/                # Сырые HTML/TXT от azbyka.ru
│   └── processed/          # Распарсенные JSON
├── tests/                  # Юнит и интеграционные тесты
└── scripts/                # Утилиты, миграции
```

## MVP — скоуп (12 недель)

**Корпус:** Октоих глас 8, ЦСЯ + греческий (~800 текстовых единиц)

**Критерии готовности:**
- F1 классификации жанров ≥ 0.88
- Precision выравнивания ≥ 0.80 (100 вручную проверенных пар)
- Recall@5 семантического поиска ≥ 0.70
- Рабочий side-by-side UI с diff

## Лицензия

Код: MIT. Тексты из azbyka.ru используются в исследовательских целях.
