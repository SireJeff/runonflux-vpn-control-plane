"""
FluxVPN i18n Package
Multi-language support with RTL handling
"""
from .translator import (
    Translator,
    get_translator,
    get_language_keyboard_data,
    t,
)

__all__ = [
    "Translator",
    "get_translator",
    "get_language_keyboard_data",
    "t",
]
