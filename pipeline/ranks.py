"""Fox ranks and the KataGo HumanSL profiles that play like them.

The table is the community table LizzieYzy Next uses for its AI coach (CoachLevel): each row lines
a Fox rank band up with a HumanSL profile, weakest first.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Rank:
    kind: str  # "K" (kyu), "D" (amateur dan) or "P" (professional dan)
    number: int

    def __str__(self) -> str:
        return f"{self.number}{self.kind}" if self.kind != "P" else f"P{self.number}D"

    def label_zh(self) -> str:
        if self.kind == "K":
            return f"{self.number}级"
        if self.kind == "D":
            return f"{self.number}段"
        return f"职业{self.number}段"


# (lowest kyu or dan covered, kind, profile), weakest first.
_LEVELS: list[tuple[str, str]] = [
    ("17-18K", "preaz_20k"),
    ("15-16K", "preaz_18k"),
    ("13-14K", "preaz_16k"),
    ("11-12K", "preaz_14k"),
    ("9-10K", "preaz_12k"),
    ("7-8K", "preaz_11k"),
    ("5-6K", "preaz_10k"),
    ("3-4K", "preaz_9k"),
    ("2K", "preaz_8k"),
    ("1K", "preaz_7k"),
    ("1D", "rank_5k"),
    ("2D", "rank_4k"),
    ("3D", "rank_3k"),
    ("4D", "rank_2k"),
    ("5D", "rank_1k"),
    ("6D", "rank_1d"),
    ("7D", "rank_3d"),
    ("8D", "rank_3d"),
    ("9D", "rank_4d"),
]


def _band_contains(band: str, rank: Rank) -> bool:
    kind = band[-1]
    if kind != rank.kind:
        return False
    numbers = [int(n) for n in band[:-1].split("-")]
    return min(numbers) <= rank.number <= max(numbers)


def level_index(rank: Rank) -> int:
    if rank.kind == "P":
        return len(_LEVELS) - 1
    if rank.kind == "K" and rank.number > 18:
        return 0
    for i, (band, _) in enumerate(_LEVELS):
        if _band_contains(band, rank):
            return i
    return len(_LEVELS) - 1


def profile_for(rank: Rank, steps_up: int = 0) -> str:
    index = max(0, min(len(_LEVELS) - 1, level_index(rank) + steps_up))
    return _LEVELS[index][1]


def from_fox_dan(raw: int) -> Rank:
    """Fox's numeric rank field: 100.. are professional dan; otherwise 17 is 1K and 18 is 1D."""
    if raw >= 100:
        return Rank("P", raw - 99)
    rank = raw - 17
    return Rank("D", rank) if rank > 0 else Rank("K", abs(rank) + 1)


_TEXT = re.compile(r"^\s*(?:职业)?(\d+)\s*(级|段|[kKdDpP])\s*$")


def parse(text: str | None) -> Rank | None:
    """Parses "8级", "3段", "8K", "3d", "职业2段"; None when unreadable."""
    if not text:
        return None
    match = _TEXT.match(text)
    if not match:
        return None
    number, unit = int(match.group(1)), match.group(2).upper()
    if text.strip().startswith("职业") or unit == "P":
        return Rank("P", number)
    if unit in ("级", "K"):
        return Rank("K", number)
    return Rank("D", number)
