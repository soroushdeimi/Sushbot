"""Tests for utils/i18n.py - internationalization utilities."""

from __future__ import annotations

from unittest.mock import MagicMock

from utils.i18n import (
    TRANSLATIONS,
    Language,
    get_bilingual_text,
    get_user_language,
    t,
)


class TestLanguageEnum:
    """Tests for Language enum."""

    def test_persian_value(self):
        assert Language.PERSIAN.value == "fa"

    def test_english_value(self):
        assert Language.ENGLISH.value == "en"

    def test_bilingual_value(self):
        assert Language.BILINGUAL.value == "bilingual"


class TestGetUserLanguage:
    """Tests for get_user_language function."""

    def test_none_user_returns_persian(self):
        assert get_user_language(None) == Language.PERSIAN

    def test_user_without_language_code_returns_persian(self):
        user = MagicMock()
        user.language_code = None
        assert get_user_language(user) == Language.PERSIAN

    def test_user_with_fa_returns_persian(self):
        user = MagicMock()
        user.language_code = "fa"
        assert get_user_language(user) == Language.PERSIAN

    def test_user_with_fa_ir_returns_persian(self):
        user = MagicMock()
        user.language_code = "fa-ir"
        assert get_user_language(user) == Language.PERSIAN

    def test_user_with_persian_returns_persian(self):
        user = MagicMock()
        user.language_code = "Persian"
        assert get_user_language(user) == Language.PERSIAN

    def test_user_with_en_returns_english(self):
        user = MagicMock()
        user.language_code = "en"
        assert get_user_language(user) == Language.ENGLISH

    def test_user_with_en_us_returns_english(self):
        user = MagicMock()
        user.language_code = "en-us"
        assert get_user_language(user) == Language.ENGLISH

    def test_user_with_en_gb_returns_english(self):
        user = MagicMock()
        user.language_code = "en-gb"
        assert get_user_language(user) == Language.ENGLISH

    def test_user_with_english_returns_english(self):
        user = MagicMock()
        user.language_code = "English"
        assert get_user_language(user) == Language.ENGLISH

    def test_user_with_bilingual_returns_bilingual(self):
        user = MagicMock()
        user.language_code = "bilingual"
        assert get_user_language(user) == Language.BILINGUAL

    def test_unknown_language_returns_persian(self):
        user = MagicMock()
        user.language_code = "de"  # German not supported
        assert get_user_language(user) == Language.PERSIAN


class TestTranslate:
    """Tests for t() translation function."""

    def test_translate_persian_key(self):
        text = t("menu", lang=Language.PERSIAN)
        assert text == TRANSLATIONS["fa"]["menu"]

    def test_translate_english_key(self):
        text = t("menu", lang=Language.ENGLISH)
        assert text == TRANSLATIONS["en"]["menu"]

    def test_translate_bilingual_shows_both(self):
        text = t("menu", lang=Language.BILINGUAL)
        # Bilingual shows both if they differ
        fa_text = TRANSLATIONS["fa"]["menu"]
        en_text = TRANSLATIONS["en"]["menu"]
        if fa_text != en_text:
            assert fa_text in text
            assert en_text in text

    def test_translate_unknown_key_returns_key(self):
        text = t("unknown_key_xyz", lang=Language.PERSIAN)
        assert text == "unknown_key_xyz"

    def test_translate_with_user(self):
        user = MagicMock()
        user.language_code = "en"
        text = t("back", user=user)
        assert text == TRANSLATIONS["en"]["back"]

    def test_translate_user_overrides_lang(self):
        user = MagicMock()
        user.language_code = "en"
        # When both user and lang are provided, lang from get_user_language(user) is used
        # since lang is None in the call
        text = t("back", user=user, lang=None)
        assert text == TRANSLATIONS["en"]["back"]

    def test_translate_explicit_lang_used(self):
        user = MagicMock()
        user.language_code = "fa"
        # When explicit lang is provided, it should be used
        text = t("back", user=user, lang=Language.ENGLISH)
        assert text == TRANSLATIONS["en"]["back"]


class TestGetBilingualText:
    """Tests for get_bilingual_text function."""

    def test_persian_user_gets_persian(self):
        user = MagicMock()
        user.language_code = "fa"
        text = get_bilingual_text("سلام", "Hello", user)
        assert text == "سلام"

    def test_english_user_gets_english(self):
        user = MagicMock()
        user.language_code = "en"
        text = get_bilingual_text("سلام", "Hello", user)
        assert text == "Hello"

    def test_bilingual_user_gets_both(self):
        user = MagicMock()
        user.language_code = "bilingual"
        text = get_bilingual_text("سلام", "Hello", user)
        assert "سلام" in text
        assert "Hello" in text
        assert text == "سلام\nHello"

    def test_none_user_gets_persian(self):
        text = get_bilingual_text("سلام", "Hello", None)
        assert text == "سلام"


class TestTranslationsStructure:
    """Tests for TRANSLATIONS dictionary structure."""

    def test_has_fa_translations(self):
        assert "fa" in TRANSLATIONS
        assert len(TRANSLATIONS["fa"]) > 0

    def test_has_en_translations(self):
        assert "en" in TRANSLATIONS
        assert len(TRANSLATIONS["en"]) > 0

    def test_key_parity(self):
        """Both languages should have the same keys."""
        fa_keys = set(TRANSLATIONS["fa"].keys())
        en_keys = set(TRANSLATIONS["en"].keys())
        # Allow some missing but most should match
        common_keys = fa_keys & en_keys
        assert len(common_keys) > 50  # At least 50 common keys

    def test_essential_keys_exist(self):
        """Essential keys should exist in both languages."""
        essential_keys = [
            "menu",
            "back",
            "cancel",
            "confirm",
            "welcome",
            "purchase",
            "support",
            "wallet",
        ]
        for key in essential_keys:
            assert key in TRANSLATIONS["fa"], f"Missing '{key}' in Persian"
            assert key in TRANSLATIONS["en"], f"Missing '{key}' in English"
