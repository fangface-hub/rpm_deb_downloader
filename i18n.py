# -*- coding: utf-8 -*-
"""国際化(i18n)モジュール."""
import json
import locale
from pathlib import Path

from pathlibex import get_app_dir


class I18n:
    """国際化クラス."""

    def __init__(self, lang=None):
        self.base_dir = Path(get_app_dir())
        if lang is None:
            lang = self._detect_system_language()
        self.lang = lang
        self.translations = {}
        self.load_translations()

    def _detect_system_language(self):
        try:
            sys_locale = locale.getlocale()[0]
            if sys_locale:
                lang = sys_locale.split('_')[0]
                if (self.base_dir / "locales" / f"{lang}.json").exists():
                    return lang
        except (ValueError, IndexError):
            pass
        return "en"

    def load_translations(self):
        locale_file = self.base_dir / "locales" / f"{self.lang}.json"
        if locale_file.exists():
            with open(locale_file, 'r', encoding='utf-8-sig') as f:
                self.translations = json.load(f)
            return

        fallback_file = self.base_dir / "locales" / "en.json"
        if fallback_file.exists():
            with open(fallback_file, 'r', encoding='utf-8-sig') as f:
                self.translations = json.load(f)

    def t(self, key, **kwargs):
        text = self.translations.get(key, key)
        return text.format(**kwargs) if kwargs else text

    def change_language(self, lang):
        self.lang = lang
        self.load_translations()

    def get_available_languages(self):
        locales_dir = self.base_dir / "locales"
        languages = []
        if not locales_dir.exists():
            return languages

        for locale_file in locales_dir.glob("*.json"):
            lang_code = locale_file.stem
            with open(locale_file, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
                lang_name = data.get("language_name", lang_code)
                languages.append({"code": lang_code, "name": lang_name})

        return sorted(languages, key=lambda x: x["code"])

    def get_current_language(self):
        return self.lang
