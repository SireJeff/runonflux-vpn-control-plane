"""Group reseller packages by subscription duration for the bot plan menu.

Pure logic — no Telegram/DB deps. Grouping is by *distinct* ``duration_days``
(no hardcoded durations), so any reseller catalog degrades gracefully.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DurationGroup:
    """One menu category: all packages sharing a ``duration_days`` value."""

    duration_days: int
    packages: list


def group_by_duration(packages) -> list[DurationGroup]:
    """Bucket ``packages`` by distinct ``duration_days``, ascending.

    Insertion order is preserved within each bucket (callers pass packages
    already ordered by ``display_order, id``).
    """
    buckets: dict[int, list] = {}
    for pkg in packages:
        buckets.setdefault(pkg.duration_days, []).append(pkg)
    return [DurationGroup(days, buckets[days]) for days in sorted(buckets)]


def duration_label(days: int) -> str:
    """Persian month label for a duration, e.g. 90 -> ``"3 ماهه"``.

    Sub-30-day durations fall back to a day label (``"7 روزه"``).
    """
    if days >= 30:
        return f"{round(days / 30)} ماهه"
    return f"{days} روزه"
