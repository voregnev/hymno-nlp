# Модель данных — Онтология атрибутов

## Атомарная единица: `:TextUnit`

Одна неделимая гимнографическая единица. Не слово, не стих.

### Структурные атрибуты (извлекаются regex)

| Атрибут | Тип | Пример | Источник |
|---|---|---|---|
| `lang` | `cu\|grc\|ru` | `cu` | метаданные |
| `book` | TEXT | `octoechos` | метаданные |
| `office` | TEXT | `matins` | regex маркеры |
| `section` | TEXT | `canon` | regex маркеры |
| `ode_number` | INT 1–9 | `3` | regex, только для canon |
| `unit_type` | TEXT | `troparion` | regex + genre detection |
| `section_order` | INT | `2` | счётчик |
| `glas` | INT 1–8 | `8` | regex |
| `day_of_week` | INT 0–6 | `0` (Вс) | regex |
| `menaion_month` | INT 1–12 | `1` | regex |
| `menaion_day` | INT 1–31 | `15` | regex |
| `pascha_offset` | INT -70..+56 | `-49` | таблица смещений |

### Лингвистические атрибуты (regex ~60–90%, LLM для остального)

| Атрибут | Метод | Пример |
|---|---|---|
| `author` | regex + LLM | `Иоанн Дамаскин` |
| `podoben` | regex | `Зватися другу Жениха` |
| `acrostic` | algorithm | `alphabetic:АБВГД` |
| `is_doxasticon` | regex | `True` |
| `is_theotokion` | regex | `False` |

### Экспертные атрибуты (ручная разметка)

| Атрибут | Пример |
|---|---|
| `translation_type` | `literal\|paraphrase\|original` |
| `theotokion_source` | `feast\|resurrection\|sunday\|weekday` |
| `author_confidence` | `high\|medium\|low` |

## Position Key

Уникальный читаемый идентификатор места в богослужении:

```
octoechos/matins/canon/g8/d0/ode3/troparion002
^         ^      ^      ^   ^   ^    ^          ^
book      office section glas dow ode  type     order
```

## Граф-схема Neo4j

```
(:Collection {name, abbrev})
    ↑ IN_COLLECTION
(:TextUnit {id, incipit, lang, genre, glas, position_key})
    → IN_TONE → (:Glas {value: 1-8})
    → IN_SECTION {order} → (:Section {key, name, office, book})
    → IN_ODE {order, unit_type} → (:Ode {key, number})
    → AUTHORED_BY {confidence} → (:Author {name})
    → MODELS_ON → (:Podoben {incipit_cu})
    → HAS_PARALLEL {similarity, method} → (:TextUnit)  # cross-lang
    → PRECEDES → (:TextUnit)  # порядок в секции
    → FOR_FEAST → (:Feast {name, date_fixed})
    → CITES → (:BiblRef {book, chapter, verse})
```

## Строфы (PostgreSQL `strophes`)

Строфы — дочерние элементы TextUnit, хранятся отдельно.
Разделитель в исходном тексте: `/`

```
text_unit: "Христа вселив в душу твою чистым твоим житием,/
            Источника жизни, священноявленне Василие,/
            реки источил еси учений благочестивых вселенней."

strophes:
  position=0: "Христа вселив в душу твою чистым твоим житием,"
  position=1: "Источника жизни, священноявленне Василие,"
  position=2: "реки источил еси учений благочестивых вселенней."
```

Строфы используются для:
- Конкорданса на уровне строки
- Анализа акростиха
- Diff-отображения при сравнении параллельных текстов
- Поэтического анализа (метрика, образный ряд)
