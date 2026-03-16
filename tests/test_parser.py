"""
tests/test_parser.py
Юнит-тесты для парсера — без сетевых вызовов и LLM.
"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from src.parser.parse_pipeline import (
    update_context_from_block,
    extract_regex_attrs,
    detect_genre,
    detect_acrostic,
    is_structural_block,
    ParsePipeline,
)


# ─── Глас ────────────────────────────────────────────────────────────────────

class TestGlasExtraction:
    def test_cu_glas_8(self):
        ctx = {}
        update_context_from_block("Глас 8. Христа вселив в душу...", "cu", ctx)
        assert ctx["glas"] == 8

    def test_cu_glas_accented(self):
        ctx = {}
        update_context_from_block("гла́с 3", "cu", ctx)
        assert ctx["glas"] == 3

    def test_grc_glas_alpha(self):
        ctx = {}
        update_context_from_block("Ἦχος αˊ. Θαῦμα θαυμάτων", "grc", ctx)
        assert ctx["glas"] == 1

    def test_grc_glas_eta(self):
        ctx = {}
        update_context_from_block("Ἦχος ηˊ", "grc", ctx)
        assert ctx["glas"] == 8

    def test_no_glas(self):
        ctx = {}
        update_context_from_block("Обычный текст без гласа", "cu", ctx)
        assert ctx.get("glas") is None


# ─── Маркеры секций ──────────────────────────────────────────────────────────

class TestSectionMarkers:
    def test_vespers_small_cu(self):
        ctx = {}
        update_context_from_block("НА МАЛОЙ ВЕЧЕРНИ", "cu", ctx)
        assert "vespers" in (ctx.get("office") or "")

    def test_matins_cu(self):
        ctx = {}
        update_context_from_block("НА УТРЕНИ", "cu", ctx)
        assert ctx.get("office") == "matins"

    def test_lihc_cu(self):
        ctx = {}
        update_context_from_block("На Господи, воззвах:", "cu", ctx)
        assert ctx.get("section") == "lihc"

    def test_canon_ode_3(self):
        ctx = {}
        update_context_from_block("Песнь 3", "cu", ctx)
        assert ctx.get("section") == "canon"
        assert ctx.get("ode_number") == 3

    def test_vespers_grc(self):
        ctx = {}
        update_context_from_block("ΕΙΣ ΤΟΝ ΜΕΓΑΝ ΕΣΠΕΡΙΝΟΝ", "grc", ctx)
        assert "vespers" in (ctx.get("office") or "")


# ─── Жанры ───────────────────────────────────────────────────────────────────

class TestGenreDetection:
    def test_hirmos_cu(self):
        assert detect_genre("Ирмос: Отверзу уста моя...", "cu") == "hirmos"

    def test_hirmos_grc(self):
        assert detect_genre("Εἱρμός· Ἀνοίξω τὸ στόμα μου", "grc") == "hirmos"

    def test_kontakion_cu(self):
        assert detect_genre("Кондак, глас 8:", "cu") == "kontakion"

    def test_stichera_by_slash(self):
        # Стихиры распознаются по наличию / (строфоразделитель)
        long_text = "Христа вселив в душу твою чистым твоим житием,/ " \
                    "Источника жизни,/ священноявленне Василие"
        assert detect_genre(long_text, "cu") == "stichera"

    def test_structural_returns_none(self):
        assert detect_genre("НА МАЛОЙ ВЕЧЕРНИ", "cu") is None


# ─── Структурные блоки ───────────────────────────────────────────────────────

class TestStructuralBlocks:
    def test_short_capslock_is_structural(self):
        assert is_structural_block("НА УТРЕНИ", "cu") is True

    def test_long_text_not_structural(self):
        long = "Христа вселив в душу твою " * 10
        assert is_structural_block(long, "cu") is False


# ─── Акростих ────────────────────────────────────────────────────────────────

class TestAcrostic:
    def test_alphabetic_acrostic(self):
        strophes = [
            "Аз грешный молюся...",
            "Благодать Твою прошу...",
            "Во веки Тебе пою...",
            "Господи, услыши мя...",
            "Даждь ми покаяние...",
        ]
        result = detect_acrostic(strophes, "cu")
        assert result is not None
        assert result.startswith("alphabetic:")

    def test_too_few_strophes(self):
        assert detect_acrostic(["А...", "Б..."], "cu") is None

    def test_grc_acrostic(self):
        strophes = [
            "Αἴνει ψυχή...",
            "Βοήθεια ἡμῶν...",
            "Γλῶσσα ἡμῶν...",
            "Δόξα σοι...",
        ]
        result = detect_acrostic(strophes, "grc")
        assert result is not None


# ─── Атрибуты ────────────────────────────────────────────────────────────────

class TestAttributeExtraction:
    def test_podoben_cu(self):
        attrs = extract_regex_attrs("Подобен: Зватися другу Жениха.", "cu")
        assert attrs.get("podoben") == "Зватися другу Жениха"

    def test_doxasticon(self):
        attrs = extract_regex_attrs("Слава, глас 2:", "cu")
        assert attrs.get("is_doxasticon") is True

    def test_theotokion(self):
        attrs = extract_regex_attrs("И ныне, праздника:", "cu")
        assert attrs.get("is_theotokion") is True

    def test_author_cu(self):
        attrs = extract_regex_attrs("Творение Иоанна Дамаскина.", "cu")
        assert attrs.get("author") is not None
        assert "Иоанн" in attrs.get("author", "")


# ─── Полный пайплайн ─────────────────────────────────────────────────────────

class TestParsePipeline:
    def test_full_block_cu(self):
        pipeline = ParsePipeline(lang="cu", book="octoechos", use_llm=False)
        # Устанавливаем контекст
        pipeline._ctx.update({
            "office": "vespers_great", "section": "lihc",
            "glas": 8, "day_of_week": 0,
        })
        block = (
            "Христа вселив в душу твою чистым твоим житием,/ "
            "Источника жизни, священноявленне Василие,/ "
            "реки источил еси учений благочестивых вселенней."
        )
        unit = pipeline.process_block(block, source_ref="test/001")
        assert unit is not None
        assert unit.lang == "cu"
        assert unit.position.glas == 8
        assert unit.position.office == "vespers_great"
        assert len(unit.strophes) == 3

    def test_structural_block_skipped(self):
        pipeline = ParsePipeline(lang="cu", book="octoechos", use_llm=False)
        unit = pipeline.process_block("НА МАЛОЙ ВЕЧЕРНИ", source_ref="test/000")
        assert unit is None

    def test_position_key_format(self):
        pipeline = ParsePipeline(lang="cu", book="octoechos", use_llm=False)
        pipeline._ctx.update({
            "office": "matins", "section": "canon",
            "ode_number": 3, "glas": 8,
        })
        block = "Ирмос: Отверзу уста моя/ и наполнятся Духа."
        unit = pipeline.process_block(block, source_ref="test/002")
        assert unit is not None
        key = unit.position.position_key()
        assert "octoechos" in key
        assert "matins" in key
        assert "ode3" in key


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
