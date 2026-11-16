"""
FluxVPN Multi-Language Translation System
JSON-based translations with RTL support for Persian and Arabic
"""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class Translator:
    """
    Multi-language translator with RTL support.
    Loads translations from JSON files and provides formatted strings.
    """

    RTL_LANGUAGES = ["fa"]
    SUPPORTED_LANGUAGES = ["en", "fa"]
    DEFAULT_LANGUAGE = "en"

    # RTL Unicode markers
    RTL_MARK = "\u200F"  # Right-to-Left Mark
    LTR_MARK = "\u200E"  # Left-to-Right Mark
    RTL_EMBEDDING = "\u202B"  # Right-to-Left Embedding
    RTL_POP = "\u202C"  # Pop Directional Formatting

    def __init__(self, locales_dir: Optional[Path] = None):
        """
        Initialize translator with locale files directory.

        Args:
            locales_dir: Path to directory containing locale JSON files.
                        Defaults to ./locales relative to this file.
        """
        if locales_dir is None:
            locales_dir = Path(__file__).parent / "locales"

        self.locales_dir = locales_dir
        self._cache: Dict[str, Dict[str, str]] = {}
        self._load_all_locales()

    def _load_all_locales(self):
        """Load all available locale files into cache"""
        if not self.locales_dir.exists():
            logger.warning(f"Locales directory not found: {self.locales_dir}")
            return

        for lang in self.SUPPORTED_LANGUAGES:
            locale_file = self.locales_dir / f"{lang}.json"
            if locale_file.exists():
                self._load_locale(lang, locale_file)
            else:
                logger.debug(f"Locale file not found: {locale_file}")

    def _load_locale(self, lang: str, filepath: Path):
        """Load a single locale file"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self._cache[lang] = json.load(f)
            logger.info(f"Loaded {len(self._cache[lang])} translations for '{lang}'")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {filepath}: {e}")
            self._cache[lang] = {}
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            self._cache[lang] = {}

    def reload(self):
        """Reload all locale files (useful for hot-reload in development)"""
        self._cache.clear()
        self._load_all_locales()

    def get(
        self,
        key: str,
        lang: Optional[str] = None,
        apply_rtl: bool = True,
        **kwargs: Any,
    ) -> str:
        """
        Get translated string for a key.

        Args:
            key: Translation key (e.g., "welcome", "error.not_found")
            lang: Language code (defaults to English)
            apply_rtl: Whether to apply RTL formatting for RTL languages
            **kwargs: Format variables to substitute in the string

        Returns:
            Translated and formatted string
        """
        lang = lang or self.DEFAULT_LANGUAGE

        # Normalize language code
        lang = lang.lower().split("-")[0]  # Handle "fa-IR" -> "fa"

        if lang not in self.SUPPORTED_LANGUAGES:
            lang = self.DEFAULT_LANGUAGE

        # Try requested language, fallback to English, then return key
        text = self._get_nested(key, lang)
        if text is None:
            text = self._get_nested(key, self.DEFAULT_LANGUAGE)
        if text is None:
            logger.warning(f"Missing translation: {key}")
            return key

        # Substitute format variables
        if kwargs:
            try:
                text = text.format(**kwargs)
            except KeyError as e:
                logger.warning(f"Missing format variable in '{key}': {e}")

        # Apply RTL formatting
        if apply_rtl and lang in self.RTL_LANGUAGES:
            text = self._apply_rtl(text)

        return text

    def _get_nested(self, key: str, lang: str) -> Optional[str]:
        """Get value from cache, supporting dot-notation for nested keys"""
        if lang not in self._cache:
            return None

        # Support nested keys like "error.not_found"
        parts = key.split(".")
        value = self._cache[lang]

        for part in parts:
            if isinstance(value, dict):
                value = value.get(part)
                if value is None:
                    return None
            else:
                return None

        return value if isinstance(value, str) else None

    def _apply_rtl(self, text: str) -> str:
        """
        Apply RTL formatting to text.
        Wraps text in RTL embedding characters for proper display.
        """
        # Simple approach: wrap entire string
        return f"{self.RTL_EMBEDDING}{text}{self.RTL_POP}"

    def is_rtl(self, lang: str) -> bool:
        """Check if a language is right-to-left"""
        return lang.lower().split("-")[0] in self.RTL_LANGUAGES

    def get_direction(self, lang: str) -> str:
        """Get text direction for a language"""
        return "rtl" if self.is_rtl(lang) else "ltr"

    def get_available_languages(self) -> Dict[str, str]:
        """Get dictionary of available languages with their native names"""
        language_names = {
            "en": "English",
            "fa": "فارسی",
            "ar": "العربية",
            "ru": "Русский",
            "zh": "中文",
        }
        return {
            lang: language_names.get(lang, lang)
            for lang in self._cache.keys()
        }

    def get_language_flag(self, lang: str) -> str:
        """Get flag emoji for a language"""
        flags = {
            "en": "🇬🇧",
            "fa": "🇮🇷",
            "ar": "🇸🇦",
            "ru": "🇷🇺",
            "zh": "🇨🇳",
        }
        return flags.get(lang, "🌐")

    def format_currency(self, amount: float, lang: str = "en") -> str:
        """Format currency amount based on locale"""
        if lang in self.RTL_LANGUAGES:
            return f"${amount:.2f}"  # Keep dollar sign in LTR for consistency
        return f"${amount:.2f}"

    def format_number(self, number: int, lang: str = "en") -> str:
        """Format number with locale-appropriate separators"""
        # For Persian, use Persian-Arabic numerals if desired
        if lang == "fa":
            # Convert to Persian numerals
            persian_digits = "۰۱۲۳۴۵۶۷۸۹"
            return "".join(persian_digits[int(d)] if d.isdigit() else d for d in f"{number:,}")
        return f"{number:,}"


# Global translator instance
_translator: Optional[Translator] = None


def get_translator() -> Translator:
    """Get or create the global translator instance"""
    global _translator
    if _translator is None:
        _translator = Translator()
    return _translator


def t(key: str, lang: str = "en", **kwargs: Any) -> str:
    """
    Shorthand function for translations.

    Usage:
        from bot.i18n import t
        message = t("welcome", "fa", name="Ali")
    """
    return get_translator().get(key, lang, **kwargs)


# Language selection helper
def get_language_keyboard_data() -> list:
    """Get data for language selection inline keyboard"""
    translator = get_translator()
    languages = translator.get_available_languages()
    return [
        {
            "code": code,
            "name": name,
            "flag": translator.get_language_flag(code),
        }
        for code, name in languages.items()
    ]
