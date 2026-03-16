"""
src/parser/parse_pipeline.py
Трёхуровневый парсер: regex → algorithm → LLM fallback.
Структурные атрибуты — только regex.
Семантические атрибуты — LLM если regex не справился.
"""
import re
import json
import logging
import argparse
import pathlib
import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional

try:
    from anthropic import Anthropic
    _anthropic_available = True
except ImportError:
    _anthropic_available = False

from dotenv import load_dotenv
import os

load_dotenv()
log = logging.getLogger(__name__)

# ─── Dataclasses ─────────────────────────────────────────────────────────────

@dataclass
class LiturgicalPosition:
    office: Optional[str] = None
    section: Optional[str] = None
    ode_number: Optional[int] = None
    unit_type: Optional[str] = None
    section_order: int = 0
    glas: Optional[int] = None
    day_of_week: Optional[int] = None
    menaion_month: Optional[int] = None
    menaion_day: Optional[int] = None
    pascha_offset: Optional[int] = None
    book: str = "unknown"

    def position_key(self) -> str:
        parts = [self.book or "?", self.office or "?", self.section or "?"]
        if self.glas:               parts.append(f"g{self.glas}")
        if self.day_of_week is not None: parts.append(f"d{self.day_of_week}")
        if self.menaion_month:      parts.append(f"{self.menaion_month:02d}-{self.menaion_day:02d}")
        if self.pascha_offset is not None: parts.append(f"p{self.pascha_offset:+d}")
        if self.ode_number:         parts.append(f"ode{self.ode_number}")
        parts.append(f"{self.unit_type or 'unk'}{self.section_order:03d}")
        return "/".join(parts)


@dataclass
class ParsedUnit:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    source_ref: str = ""
    lang: str = "cu"
    raw_text: str = ""
    strophes: list[str] = field(default_factory=list)
    position: LiturgicalPosition = field(default_factory=LiturgicalPosition)

    # Атрибуты
    genre: Optional[str] = None
    author: Optional[str] = None
    author_confidence: str = "low"
    podoben: Optional[str] = None
    acrostic: Optional[str] = None
    translation_type: Optional[str] = None
    is_doxasticon: bool = False
    is_theotokion: bool = False
    theotokion_source: Optional[str] = None

    # Служебные
    parse_method: dict = field(default_factory=dict)
    needs_review: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["position_key"] = self.position.position_key()
        return d


# ─── Regex маркеры ───────────────────────────────────────────────────────────

SECTION_MARKERS_CU = [
    (r'НА\s+МАЛОЙ\s+ВЕЧЕРНИ',                  'vespers', 'small',      None),
    (r'НА\s+ВЕЛИК[ОА][ЙИ]\s+ВЕЧЕРНИ',          'vespers', 'great',      None),
    (r'НА\s+УТРЕНИ',                            'matins',  None,         None),
    (r'НА\s+ПОВЕЧЕРИИ',                         'compline',None,         None),
    (r'НА\s+ПОЛУНОЩНИЦЕ',                       'midnight',None,         None),
    (r'НА\s+ЛИТУРГИИ',                          'liturgy', None,         None),
    (r'На\s+Го́?споди,?\s+воззва́?х',            None,      'lihc',       None),
    (r'На\s+стихо́?вне',                        None,      'aposticha',  None),
    (r'На\s+хвали́?тех',                        None,      'praises',    None),
    (r'По\s+([123])-?м\s+стихосло́?вии',        None,      'kathisma',   None),
    (r'[Пп]е́?снь\s+(\d)',                      None,      'canon',      r'\1'),  # ода
    (r'[Кк]ата\s*ва́?сиа',                     None,      'canon',      None),
]

SECTION_MARKERS_GRC = [
    (r'ΕΙΣ\s+ΤΗΝ\s+ΜΙΚΡΑΝ\s+ΕΣΠΕΡΙΝΟ[ΝΣ]',   'vespers', 'small',      None),
    (r'ΕΙΣ\s+ΤΟΝ\s+ΜΕΓΑΝ\s+ΕΣΠΕΡΙΝΟΝ',        'vespers', 'great',      None),
    (r'ΕΙΣ\s+ΤΟΝ\s+ΟΡΘΡΟΝ',                   'matins',  None,         None),
    (r'ΕΙΣ\s+ΤΗΝ\s+ΛΕΙΤΟΥΡΓΙΑΝ',             'liturgy', None,         None),
    (r'Εἰς\s+τό,?\s*Κύριε\s+ἐκέκραξα',        None,      'lihc',       None),
    (r'Εἰς\s+τ[αὰ]\s+[Ἀα]πόστιχα',           None,      'aposticha',  None),
    (r'Εἰς\s+τοὺς\s+Αἴνους',                  None,      'praises',    None),
    (r'ᾨδ[ὴη]\s+(\w+)[.,·]',                  None,      'canon',      r'\1'),
    (r'Εἱρμός[:\s·]',                          None,      'canon',      None),
]

GLAS_CU  = re.compile(r'[Гг]ла́?с\s+(\d)', re.UNICODE)
GLAS_GRC = re.compile(r'Ἦχος\s+([αβγδεζηθ])ˊ?', re.UNICODE)
GRC_GLAS_MAP = {'α':1,'β':2,'γ':3,'δ':4,'ε':5,'ζ':6,'η':7,'θ':8}

DOW_CU = {
    'воскресен': 0, 'недел': 0,
    'понедельн': 1,
    'вторн': 2,
    'сред': 3,
    'четвер': 4,
    'пятн': 5,
    'суббот': 6,
}

PODOBEN_CU  = re.compile(r'[Пп]одо́?бен[:\s]+(.{5,80}?)(?:\n|\.)', re.UNICODE)
PODOBEN_GRC = re.compile(r'Πρὸς\s+(.{5,80}?)(?:\n|·)', re.UNICODE)
AUTHOR_CU   = re.compile(r'[Тт]воре́?ние\s+([\w\s]{3,40}?)[\.\n]|([А-ЯЁ][\w]+иево):', re.UNICODE)
DOXASTICON  = re.compile(r'[Сс]ла́?ва[,\s]|Δόξα\b', re.UNICODE)
THEOTOKION  = re.compile(r'[Ии]\s+ны́?не|Καὶ\s+νῦν\b', re.UNICODE)

GENRE_PATTERNS_CU = [
    (r'[Ии]рмо́?с',       'hirmos'),
    (r'[Кк]онда́?к',      'kontakion'),
    (r'[Кк]ата\s*васиа',  'katavasia'),
    (r'[Сс]еда́?лен',     'kathisma_hymn'),
    (r'[Сс]вети́?лен|[Ее]кзапостила́?р', 'exapostilarion'),
    (r'[Тт]ропа́?р',      'troparion'),
    (r'[Сс]тихи́?р',      'stichera'),
]
GENRE_PATTERNS_GRC = [
    (r'Εἱρμός',           'hirmos'),
    (r'Κοντάκιον',        'kontakion'),
    (r'Κατα[βν]ασ',       'katavasia'),
    (r'Κάθισμα',          'kathisma_hymn'),
    (r'Φωταγωγικόν|Ἐξαποστειλάριον', 'exapostilarion'),
    (r'Τροπάριον',        'troparion'),
    (r'Στιχηρ',           'stichera'),
]

CU_ALPHABET  = "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
GRC_ALPHABET = "ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ"

TRIODION_OFFSETS = {
    "мытаре": -70, "блудного": -63, "мясопустн": -56,
    "сыропустн": -49, "первой недел": -42, "второй недел": -35,
    "третьей недел": -28, "четвертой недел": -21, "пятой недел": -14,
    "шестой недел": -7, "пасх": 0, "антипасх": 7,
    "всех святых": 56,
}


# ─── Уровень 1: Regex ────────────────────────────────────────────────────────

def update_context_from_block(block: str, lang: str, ctx: dict):
    """Обновляет контекст из структурных маркеров блока. Мутирует ctx."""
    markers = SECTION_MARKERS_CU if lang == "cu" else SECTION_MARKERS_GRC

    for pattern, office, section, ode_group in markers:
        m = re.search(pattern, block, re.IGNORECASE | re.UNICODE)
        if m:
            if office:
                suffix = section or ""
                ctx["office"] = f"{office}_{suffix}".rstrip("_")
            if section:
                ctx["section"] = section
            if ode_group:
                try:
                    ctx["ode_number"] = int(m.expand(ode_group))
                except (IndexError, ValueError):
                    pass
            break

    # Глас
    gm = (GLAS_CU if lang == "cu" else GLAS_GRC).search(block)
    if gm:
        raw = gm.group(1)
        ctx["glas"] = GRC_GLAS_MAP.get(raw.rstrip('ˊ'), None) \
                      if lang == "grc" else int(raw)

    # День недели (только ЦСЯ)
    if lang == "cu":
        block_l = block.lower()
        for kw, dow in DOW_CU.items():
            if kw in block_l:
                ctx["day_of_week"] = dow
                break

    # Пасхальное смещение (Триодь)
    block_l = block.lower()
    for kw, offset in TRIODION_OFFSETS.items():
        if kw in block_l:
            ctx["pascha_offset"] = offset
            break


def extract_regex_attrs(block: str, lang: str) -> dict:
    result = {}
    pm = (PODOBEN_CU if lang == "cu" else PODOBEN_GRC).search(block)
    if pm:
        result["podoben"] = pm.group(1).strip()
        result["parse_method_podoben"] = "regex"
    am = AUTHOR_CU.search(block) if lang == "cu" else None
    if am:
        result["author"] = (am.group(1) or am.group(2) or "").strip()
        result["author_confidence"] = "high"
        result["parse_method_author"] = "regex"
    result["is_doxasticon"] = bool(DOXASTICON.search(block))
    result["is_theotokion"] = bool(THEOTOKION.search(block))
    return result


def detect_genre(block: str, lang: str) -> Optional[str]:
    patterns = GENRE_PATTERNS_CU if lang == "cu" else GENRE_PATTERNS_GRC
    for pat, genre in patterns:
        if re.search(pat, block, re.IGNORECASE | re.UNICODE):
            return genre
    if '/' in block and len(block) > 80:
        return "stichera"
    return None


def is_structural_block(block: str, lang: str) -> bool:
    """True если блок — структурный маркер, а не текстовая единица."""
    markers = SECTION_MARKERS_CU if lang == "cu" else SECTION_MARKERS_GRC
    for pattern, *_ in markers:
        if re.search(pattern, block, re.IGNORECASE | re.UNICODE):
            if len(block) < 200:
                return True
    return False


# ─── Уровень 2: Алгоритм (акростих) ─────────────────────────────────────────

def detect_acrostic(strophes: list[str], lang: str) -> Optional[str]:
    if len(strophes) < 4:
        return None
    alphabet = CU_ALPHABET if lang == "cu" else GRC_ALPHABET
    first_letters = []
    for s in strophes:
        s = s.strip()
        for ch in s:
            if ch.upper() in alphabet:
                first_letters.append(ch.upper())
                break
    if not first_letters:
        return None
    candidate = "".join(first_letters)
    if candidate == alphabet[:len(candidate)] and len(candidate) >= 4:
        return f"alphabetic:{candidate}"
    vowels = set("АЕЁИОУЫЭЮЯІѢꙊ") if lang == "cu" else set("ΑΕΗΙΟΥΩ")
    has_vowel = any(c in vowels for c in candidate)
    has_cons  = any(c not in vowels for c in candidate)
    if 4 <= len(candidate) <= 14 and has_vowel and has_cons:
        return f"named:{candidate}"
    return None


# ─── Уровень 3: LLM fallback ─────────────────────────────────────────────────

LLM_SYSTEM = (
    "Ты эксперт по православной гимнографии. "
    "Анализируй литургические тексты и извлекай ТОЛЬКО запрошенные атрибуты. "
    "Отвечай ТОЛЬКО валидным JSON без объяснений. "
    "Если атрибут не определяется — используй null. "
    "Confidence: high | medium | low."
)

FIELD_DESCRIPTIONS = {
    "author":           "автор текста (имя или null если анонимно/неизвестно)",
    "genre":            "жанр: stichera|troparion|kontakion|hirmos|kathisma_hymn|exapostilarion|katavasia",
    "translation_type": "тип: literal|paraphrase|original",
    "biblical_refs":    "список {book,chapter,verse} или []",
}


class LLMFallback:
    def __init__(self, enabled: bool = True, budget: int = 500):
        self.enabled = enabled and _anthropic_available
        self.budget = budget
        self.calls = 0
        self._failures = 0
        self._circuit_open = False
        self._client = Anthropic() if self.enabled else None

    def _can_call(self, fields: set) -> bool:
        if not self.enabled or self._circuit_open or not fields:
            return False
        if self.calls >= self.budget:
            log.warning("LLM budget exhausted")
            return False
        return True

    def extract(self, block: str, lang: str, fields: set, ctx: dict) -> dict:
        if not self._can_call(fields):
            return {}

        lang_label = "церковнославянском" if lang == "cu" else "греческом"
        requested = {k: FIELD_DESCRIPTIONS[k] for k in fields if k in FIELD_DESCRIPTIONS}
        prompt = (
            f"Текст на {lang_label} языке:\n\n<text>\n{block[:600]}\n</text>\n\n"
            f"Контекст: {json.dumps(ctx, ensure_ascii=False)}\n\n"
            f"Извлеки:\n{json.dumps(requested, ensure_ascii=False, indent=2)}\n\n"
            f'Ответь JSON: {{"extracted":{{...}},"confidence":{{"field":"high|medium|low"}}}}'
        )

        try:
            resp = self._client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=400,
                system=LLM_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = resp.content[0].text.strip()
            raw = re.sub(r'^```json\s*|\s*```$', '', raw, flags=re.DOTALL)
            data = json.loads(raw)
            result = data.get("extracted", {})
            confidence = data.get("confidence", {})
            self.calls += 1
            self._failures = 0

            out = {}
            for k, v in result.items():
                if v is not None:
                    out[k] = v
                    conf = confidence.get(k, "medium")
                    out[f"{k}__confidence"] = conf
                    if conf == "low":
                        out[f"{k}__needs_review"] = True
            return out

        except Exception as e:
            self._failures += 1
            if self._failures >= 5:
                self._circuit_open = True
                log.error("LLM circuit breaker opened")
            log.error(f"LLM extract error: {e}")
            return {}


# ─── Главный класс ───────────────────────────────────────────────────────────

class ParsePipeline:
    def __init__(self, lang: str, book: str, use_llm: bool = True, llm_budget: int = 500):
        self.lang = lang
        self.book = book
        self.llm = LLMFallback(enabled=use_llm, budget=llm_budget)
        self._ctx: dict = {
            "office": None, "section": None, "ode_number": None,
            "glas": None, "day_of_week": None, "pascha_offset": None,
            "section_counters": {},
        }

    def _section_order(self) -> int:
        key = (self._ctx.get("office"), self._ctx.get("section"), self._ctx.get("ode_number"))
        self._ctx["section_counters"][key] = self._ctx["section_counters"].get(key, 0) + 1
        return self._ctx["section_counters"][key]

    def process_block(self, block: str, source_ref: str = "") -> Optional[ParsedUnit]:
        block = block.strip()
        if len(block) < 20:
            return None

        # Обновляем контекст структурными маркерами
        update_context_from_block(block, self.lang, self._ctx)

        # Если это только структурный маркер — пропускаем
        if is_structural_block(block, self.lang):
            return None

        unit = ParsedUnit(
            source_ref=source_ref,
            lang=self.lang,
            raw_text=block,
        )

        # Позиция
        unit.position = LiturgicalPosition(
            book=self.book,
            office=self._ctx.get("office"),
            section=self._ctx.get("section"),
            ode_number=self._ctx.get("ode_number"),
            section_order=self._section_order(),
            glas=self._ctx.get("glas"),
            day_of_week=self._ctx.get("day_of_week"),
            pascha_offset=self._ctx.get("pascha_offset"),
        )

        # Строфы
        unit.strophes = [s.strip() for s in re.split(r'/+', block) if s.strip()]

        # Regex атрибуты
        regex_attrs = extract_regex_attrs(block, self.lang)
        for k, v in regex_attrs.items():
            if not k.startswith("parse_method_"):
                setattr(unit, k, v) if hasattr(unit, k) else None
                unit.parse_method[k] = "regex"

        # Жанр через regex
        genre = detect_genre(block, self.lang)
        if genre:
            unit.genre = genre
            unit.position.unit_type = genre
            unit.parse_method["genre"] = "regex"

        # Акростих
        acrostic = detect_acrostic(unit.strophes, self.lang)
        if acrostic:
            unit.acrostic = acrostic
            unit.parse_method["acrostic"] = "algorithm"

        # LLM fallback для недостающих атрибутов
        llm_needed = set()
        if not unit.author:
            llm_needed.add("author")
        if not unit.genre:
            llm_needed.add("genre")

        if llm_needed:
            llm_ctx = {
                "glas":    unit.position.glas,
                "section": unit.position.section,
                "office":  unit.position.office,
            }
            llm_result = self.llm.extract(block, self.lang, llm_needed, llm_ctx)
            for k, v in llm_result.items():
                if k.endswith("__confidence") or k.endswith("__needs_review"):
                    continue
                base_k = k
                if hasattr(unit, base_k):
                    setattr(unit, base_k, v)
                    unit.parse_method[base_k] = "llm"
            if any(k.endswith("__needs_review") for k in llm_result):
                unit.needs_review = True

        return unit

    def process_file(self, path: pathlib.Path) -> list[ParsedUnit]:
        text = path.read_text(encoding="utf-8")
        blocks = [b.strip() for b in re.split(r'\n{2,}', text) if b.strip()]
        units = []
        for i, block in enumerate(blocks):
            ref = f"{path.parent.name}/{path.stem}/b{i:04d}"
            unit = self.process_block(block, source_ref=ref)
            if unit:
                units.append(unit)
        return units


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", nargs="+", required=True,
                        help="Input directories (data/raw/oktoih_cu ...)")
    parser.add_argument("--out", default="data/processed", help="Output JSONL directory")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM fallback")
    parser.add_argument("--llm-budget", type=int, default=500)
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    BOOK_META = {
        "oktoih_cu":     ("cu",  "octoechos"),
        "oktoih_grc":    ("grc", "octoechos"),
        "mineja_jan_cu": ("cu",  "menaion"),
        "mineja_jan_grc":("grc", "menaion"),
        "triodion_cu":   ("cu",  "triodion"),
    }

    for input_path_str in args.input:
        input_dir = pathlib.Path(input_path_str)
        book_key = input_dir.name
        lang, book = BOOK_META.get(book_key, ("cu", "unknown"))

        pipeline = ParsePipeline(
            lang=lang, book=book,
            use_llm=not args.no_llm,
            llm_budget=args.llm_budget,
        )

        out_file = out_dir / f"{book_key}.jsonl"
        count = 0
        with open(out_file, "w", encoding="utf-8") as f:
            for txt_file in sorted(input_dir.glob("*.txt")):
                units = pipeline.process_file(txt_file)
                for u in units:
                    f.write(json.dumps(u.to_dict(), ensure_ascii=False) + "\n")
                    count += 1

        log.info(f"{book_key}: {count} units → {out_file}")
        log.info(f"  LLM calls: {pipeline.llm.calls} / {pipeline.llm.budget}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
