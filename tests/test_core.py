"""
Tests for core modules: converter and layout loader.
"""

import json
import os
import tempfile
import pytest

from src.core.converter import TextConverter
from src.core.layout_loader import LayoutConfig, _invert_mapping, _find_source_name, INVERT_MARKER

# sample layouts with _invert marker

SAMPLE_LAYOUTS = {
    "layouts": [
        {
            "id": "en_ua",
            "name": "English ↔ Ukrainian",
            "layout_ids": {
                "windows": ["00000409", "00000422"],
            },
            "mappings": {
                "en_to_ua": {
                    "q": "й", "w": "ц", "e": "у", "r": "к", "t": "е",
                    "y": "н", "u": "г", "i": "ш", "o": "щ", "p": "з",
                    "a": "ф", "s": "і", "d": "в", "f": "а", "g": "п",
                    "h": "р", "j": "о", "k": "л", "l": "д",
                    "z": "я", "x": "ч", "c": "с", "v": "м", "b": "и",
                    "n": "т", "m": "ь",
                    "Q": "Й", "W": "Ц", "E": "У", "R": "К", "T": "Е",
                    "Y": "Н", "U": "Г", "I": "Ш", "O": "Щ", "P": "З",
                    "A": "Ф", "S": "І", "D": "В", "F": "А", "G": "П",
                    "H": "Р", "J": "О", "K": "Л", "L": "Д",
                    "Z": "Я", "X": "Ч", "C": "С", "V": "М", "B": "И",
                    "N": "Т", "M": "Ь",
                },
                "ua_to_en": "_invert",
            },
        },
    ]
}


@pytest.fixture
def config_path():
    """Creates a temporary JSON with test layouts."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(SAMPLE_LAYOUTS, f, ensure_ascii=False)
        fpath = f.name
    yield fpath
    os.unlink(fpath)


@pytest.fixture
def config(config_path):
    return LayoutConfig(config_path)


@pytest.fixture
def converter(config):
    return TextConverter(config)


# LayoutConfig tests


class TestLayoutConfig:
    def test_load_layouts(self, config):
        assert len(config.layouts) == 1

    def test_get_active_defaults_to_true(self, config):
        active = config.get_active()  # no filter -> all layouts
        assert len(active) == 1
        assert active[0]["id"] == "en_ua"

    def test_get_active_filtered(self, config):
        """Filter by specific layout IDs."""
        active = config.get_active(active_ids=["en_ua"])
        assert len(active) == 1
        assert config.get_active(active_ids=["nonexistent"]) == []

    def test_get_by_id(self, config):
        layout = config.get_by_id("en_ua")
        assert layout is not None
        assert layout["name"] == "English ↔ Ukrainian"

    def test_get_by_id_not_found(self, config):
        assert config.get_by_id("nonexistent") is None

    def test_get_mapping(self, config):
        mapping = config.get_mapping("en_ua", "en_to_ua")
        assert mapping["q"] == "й"
        assert mapping["a"] == "ф"

    def test_get_mapping_not_found(self, config):
        with pytest.raises(ValueError):
            config.get_mapping("en_ua", "nonexistent")

    def test_get_all_mappings(self, config):
        mappings = config.get_all_mappings("en_ua")
        assert "en_to_ua" in mappings
        assert "ua_to_en" in mappings

    def test_invert_marker_creates_reverse(self, config):
        """ua_to_en is '_invert', should be auto-generated as dict."""
        ua_to_en = config.get_mapping("en_ua", "ua_to_en")
        assert isinstance(ua_to_en, dict)
        en_to_ua = config.get_mapping("en_ua", "en_to_ua")
        for en, ua in en_to_ua.items():
            assert ua_to_en[ua] == en

    def test_mappings_are_symmetric(self, config):
        fwd = config.get_mapping("en_ua", "en_to_ua")
        rev = config.get_mapping("en_ua", "ua_to_en")
        for en, ua in fwd.items():
            assert rev[ua] == en
        for ua, en in rev.items():
            assert fwd[en] == ua


# _invert_mapping unit tests


class TestInvertMapping:
    def test_basic_inversion(self):
        m = {"a": "1", "b": "2"}
        result = _invert_mapping(m)
        assert result == {"1": "a", "2": "b"}

    def test_inverse_of_inverse_is_original(self):
        m = {"a": "1", "b": "2", "c": "3"}
        assert _invert_mapping(_invert_mapping(m)) == m

    def test_duplicate_values_raise(self):
        m = {"a": "1", "b": "1"}
        with pytest.raises(ValueError, match="duplicate value"):
            _invert_mapping(m)


class TestFindSourceName:
    def test_finds_pair(self):
        m = {"en_to_ua": {"q": "й"}, "de_to_fr": {"a": "b"}}
        assert _find_source_name(m, "ua_to_en") == "en_to_ua"
        assert _find_source_name(m, "fr_to_de") == "de_to_fr"

    def test_ignores_other_markers(self):
        m = {"en_to_ua": {"q": "й"}, "ua_to_en": "_invert", "fr_to_de": "_invert"}
        assert _find_source_name(m, "ua_to_en") == "en_to_ua"
        assert _find_source_name(m, "fr_to_de") is None

    def test_no_source(self):
        assert _find_source_name({"ua_to_en": "_invert"}, "ua_to_en") is None


# TextConverter tests


class TestTextConverter:
    def test_convert_en_to_ua_simple(self, converter):
        result = converter.convert("ghbdsn", "en_ua", "en_to_ua")
        assert result == "привіт"

    def test_convert_ua_to_en_simple(self, converter):
        result = converter.convert("привіт", "en_ua", "ua_to_en")
        assert result == "ghbdsn"

    def test_convert_en_to_ua_sentence(self, converter):
        result = converter.convert("ghbdtn", "en_ua", "en_to_ua")
        assert result == "привет"

    def test_convert_auto_by_content(self, converter):
        """Auto-detect: Latin text -> convert to UA."""
        result = converter.convert_auto("ghbdsn", "en_ua")
        assert result == "привіт"

    def test_convert_auto_by_layout(self, converter):
        """Auto-detect: if current layout is UA, text was typed in EN."""
        result = converter.convert_auto("ghbdsn", "en_ua", current_layout_id="00000422")
        assert result == "привіт"

    def test_convert_with_unknown_chars(self, converter):
        result = converter.convert("ghbdsn123!", "en_ua", "en_to_ua")
        assert result == "привіт123!"

    def test_convert_empty_string(self, converter):
        assert converter.convert("", "en_ua", "en_to_ua") == ""

    def test_convert_case_sensitive(self, converter):
        result = converter.convert("GHBDSN", "en_ua", "en_to_ua")
        assert result == "ПРИВІТ"

    def test_inverse_conversion(self, converter):
        original = "Hello, World! 123"
        ua = converter.convert(original, "en_ua", "en_to_ua")
        back = converter.convert(ua, "en_ua", "ua_to_en")
        assert back == original

    def test_uppercase_ukrainian(self, converter):
        result = converter.convert("ДОБРИЙДЕНЬ", "en_ua", "ua_to_en")
        assert result == "LJБHBQLTYM"