# Источники греческого корпуса

## Основной источник: azbyka.ru

Портал содержит греческие литургические тексты в том же формате что и ЦСЯ.
Источник для Октоиха — Παρακλητική, Βενετία 1858 (Venice edition).
Источник для Миней — синодальные греческие издания.

### URL-паттерны

| Книга | URL-паттерн | Страниц |
|---|---|---|
| Октоих (Παρακλητική) | `/otechnik/greek/oktoih-na-grecheskom-jazyke/{n}` | ~14 |
| Минея январь | `/otechnik/greek/mineja-yanvar-na-grecheskom-jazyke/{n}` | ~40 |
| Минея февраль | `/otechnik/greek/mineja-fevral-na-grecheskom-jazyke/{n}` | ~40 |
| Минея март | `/otechnik/greek/mineja-mart-na-grecheskom-jazyke/{n}` | ~40 |
| Минея апрель | `/otechnik/greek/mineja-aprel-na-grecheskom-jazyke/{n}` | ~40 |
| Минея май | `/otechnik/greek/mineja-maj-na-grecheskom-jazyke/{n}` | ~50 |
| Минея июнь | `/otechnik/greek/mineja-iyun-na-grecheskom-jazyke/{n}` | ~40 |
| Минея июль | `/otechnik/greek/mineja-iyul-na-grecheskom-jazyke/{n}` | ~40 |
| Минея август | `/otechnik/greek/mineja-avgust-na-grecheskom-jazyke/{n}` | ~50 |
| Минея сентябрь | `/otechnik/greek/mineja-sentyabr-na-grecheskom-jazyke/{n}` | ~40 |
| Минея октябрь | `/otechnik/greek/mineja-oktyabr-na-grecheskom-jazyke/{n}` | ~40 |
| Минея ноябрь | `/otechnik/greek/mineja-noyabr-na-grecheskom-jazyke/{n}` | ~40 |
| Минея декабрь | `/otechnik/greek/mineja-dekabr-na-grecheskom-jazyke/{n}` | ~50 |

### Особенности греческого текста

- Политоническая орфография (ударения: острое, облечённое, тупое)
- Придыхания (густое ᾿, тонкое ᾽)
- Unicode NFC, блоки: Greek, Greek Extended, Combining Diacritical Marks
- Разделители строф: `·` (средняя точка) или `,` — в отличие от `/` в ЦСЯ
- Маркеры секций: КАПСЛОК греческими буквами (ΕΙΣ ΤΟΝ ΟΡΘΡΟΝ и т.д.)
- Глас: `Ἦχος αˊ` ... `Ἦχος ηˊ`

### Соответствие гласов

| ЦСЯ | Греч. | Число |
|---|---|---|
| Глас 1 | Ἦχος αˊ | 1 |
| Глас 2 | Ἦχος βˊ | 2 |
| Глас 3 | Ἦχος γˊ | 3 |
| Глас 4 | Ἦχος δˊ | 4 |
| Глас 5 (plagal 1) | Ἦχος πλ. αˊ / εˊ | 5 |
| Глас 6 (plagal 2) | Ἦχος πλ. βˊ / ζˊ | 6 |
| Глас 7 (grave) | Ἦχος βαρύς / ηˊ | 7 |
| Глас 8 (plagal 4) | Ἦχος πλ. δˊ / θˊ | 8 |

## Резервные источники

### Internet Archive — Παρακλητική (1858)

```
URL: https://archive.org/details/Oktoih_20221222_222250_744815
Файлы:
  Παρακλητική ήτοι Οκτώηχος η Μεγάλη (1858).pdf     — оригинал
  Παρακλητική ήτοι Οκτώηχος η Μεγάλη (1858)_hocr_searchtext.txt.gz — OCR текст
```

Качество OCR: низкое (~15–20% ошибок), использовать только как резерв.

### Thesaurus Linguae Graecae (TLG)

- URL: https://stephanus.tlg.uci.edu/
- Содержит Analecta Hymnica Graeca и патристические тексты
- **Требует подписки** (~$150/год для индивидуалов)
- Применим для Alpha+ при необходимости более глубокого греческого корпуса

### goarch.org — Digital Chant Stand

- URL: https://digitalchantstand.goarch.org/
- Современный греческий + английский переводы
- Структурирован по дням богослужебного календаря
- Не Byzantine Greek, но полезен для английских параллелей

### English Analogion

- URL: https://englishanalogion.com/
- Английские переводы с Byzantine chant notation
- Полезен для трёхъязычного сравнения (ЦСЯ / греч. / англ.)

## Стратегия для MVP

**Использовать только azbyka.ru** — этого достаточно для глас 8 Октоиха.

```bash
# MVP: только Октоих
python src/scraper/scrape.py --book oktoih_cu --book oktoih_grc

# Alpha: добавить Минею январь (Обрезание + Василий Великий)
python src/scraper/scrape.py --book mineja_jan_cu --book mineja_jan_grc
```

Преимущества azbyka.ru как источника:
1. Те же URL-паттерны для ЦСЯ и греч. — один парсер
2. Источник Greek: Venice 1858 — максимально близок к ЦСЯ переводу
3. Unicode NFC, нет проблем с кодировкой
4. Политоническая орфография сохранена
5. Структурные маркеры явные (КАПСЛОК, рубрики)
