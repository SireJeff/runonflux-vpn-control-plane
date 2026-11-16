"""RTL (Persian) readability helpers for the end-user bot.

Telegram derives a line's base direction from its first strong character, and
the Unicode Bidi Algorithm reorders weak/neutral runs (Western digits, ``·``,
Latin words) relative to strong RTL runs — so numbers migrate to a phrase
boundary and field order scrambles. These helpers keep the source digits and
Latin tokens exactly where they are composed:

- ``num`` / ``ltr`` wrap a run in First-Strong Isolate (U+2068) … Pop
  Directional Isolate (U+2069). An isolated run renders left-to-right
  internally but is a single neutral atom externally, so it stays put.
- ``rtl_line`` prepends a Right-to-Left Mark (U+200F) to force RTL base
  direction on lines/labels that could otherwise start with a Latin word or
  digit.

Pure module — no imports beyond the standard library, no Telegram/DB deps.
"""

FSI = "⁨"  # First-Strong Isolate
PDI = "⁩"  # Pop Directional Isolate
RLM = "‏"  # Right-to-Left Mark


def num(value) -> str:
    """Format an int-convertible value with thousands separators, isolated.

    ``num(150000)`` -> ``"⁨150,000⁩"``. The digit run stays contiguous
    and cannot migrate to a phrase boundary.
    """
    return f"{FSI}{int(value):,}{PDI}"


def num_unit(value, unit: str) -> str:
    """Isolate a number together with its unit as ONE atom.

    ``num`` isolates only the digits, which is not enough for a mid-line field
    like ``"30 گیگ"``: the bare unit word ``گیگ`` is the only strong-RTL run and
    the bidi algorithm reorders the neutral digit run away from it (the number
    detaches from its unit). Wrapping ``"30 گیگ"`` in a single FSI…PDI isolate
    makes number+unit one inseparable neutral atom, so they stay glued and
    ordered correctly. ``num_unit(30, "گیگ")`` -> ``"⁨30 گیگ⁩"``.
    """
    return f"{FSI}{int(value):,} {unit}{PDI}"


def ltr(token: str) -> str:
    """Isolate a Latin token (e.g. a plan name) so it does not flip the run."""
    return f"{FSI}{token}{PDI}"


def rtl_line(text: str) -> str:
    """Force RTL base direction for a line/label that may start with Latin/digit."""
    return f"{RLM}{text}"
