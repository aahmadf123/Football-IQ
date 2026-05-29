"""Signal 1 — personnel grouping from jersey numbers (Issue #135).

NCAA jersey-number conventions map a number to a likely position family:

    OL  50–79
    QB  1–19  (also WR/DB range; QB resolved by roster when available)
    RB  20–49
    WR  10–19 / 80–89
    TE  40–49 / 80–89

Personnel is reported in coaching shorthand ``"{n_RB}{n_TE}"`` (e.g. ``"11"`` =
1 RB + 1 TE + 3 WR, ``"21"`` = 2 RB + 1 TE + 2 WR). The remaining skill players
are WRs. We prefer an explicit roster position (from the ``players`` table) and
fall back to the jersey range only when the roster has no entry — the
"learned-role fallback" hook in the issue. Confidence reflects how many of the
11 offensive players had a *resolved* position.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

# Position family inferred purely from jersey number (NCAA ranges). Overlapping
# ranges (e.g. 40–49 TE/RB, 80–89 WR/TE) are resolved by roster position first.
_JERSEY_RANGES: list[tuple[int, int, str]] = [
    (0, 9, "QB"),     # 0–9: QB (also some WR/DB; roster disambiguates)
    (10, 19, "WR"),
    (20, 39, "RB"),
    (40, 49, "RB"),   # 40–49 leans RB (FB) but can be TE; roster wins
    (50, 79, "OL"),
    (80, 89, "WR"),   # 80–89 WR/TE; roster wins
    (90, 99, "DL"),
]

SKILL_POSITIONS = frozenset({"QB", "RB", "TE", "WR"})


def position_from_jersey(number: int | None) -> str | None:
    """Best-effort NCAA position family for a jersey number, or ``None``."""
    if number is None:
        return None
    for lo, hi, pos in _JERSEY_RANGES:
        if lo <= number <= hi:
            return pos
    return None


@dataclass
class PersonnelSignal:
    """Personnel grouping result with a one-hot-friendly grouping label."""

    grouping: str                  # coaching shorthand e.g. "11", "12", "21"
    n_rb: int
    n_te: int
    n_wr: int
    n_qb: int
    n_ol: int
    confidence: float              # fraction of 11 with a resolved position
    resolved_count: int
    source: str                    # "roster" | "jersey" | "mixed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "grouping": self.grouping,
            "n_rb": self.n_rb,
            "n_te": self.n_te,
            "n_wr": self.n_wr,
            "n_qb": self.n_qb,
            "n_ol": self.n_ol,
            "confidence": self.confidence,
            "resolved_count": self.resolved_count,
            "source": self.source,
        }


def extract_personnel(players: list[dict[str, Any]]) -> PersonnelSignal:
    """Compute the personnel grouping for the offensive 11.

    Each player dict may carry ``position`` (roster) and/or ``jersey_number``.
    Roster position is authoritative; jersey range is the fallback.
    """
    counts: Counter[str] = Counter()
    resolved = 0
    used_roster = False
    used_jersey = False

    for p in players:
        pos = (p.get("position") or "").upper().strip() or None
        if pos in {"FB"}:
            pos = "RB"
        if pos and pos in {"QB", "RB", "TE", "WR", "OL", "C", "G", "T"}:
            if pos in {"C", "G", "T"}:
                pos = "OL"
            counts[pos] += 1
            resolved += 1
            used_roster = True
            continue
        # Fallback to jersey range.
        inferred = position_from_jersey(p.get("jersey_number"))
        if inferred and inferred in {"QB", "RB", "TE", "WR", "OL"}:
            counts[inferred] += 1
            resolved += 1
            used_jersey = True

    n_total = max(len(players), 1)
    n_rb = counts.get("RB", 0)
    n_te = counts.get("TE", 0)
    n_wr = counts.get("WR", 0)
    n_qb = counts.get("QB", 0)
    n_ol = counts.get("OL", 0)

    grouping = f"{n_rb}{n_te}"
    confidence = round(resolved / n_total, 3)
    if used_roster and used_jersey:
        source = "mixed"
    elif used_roster:
        source = "roster"
    elif used_jersey:
        source = "jersey"
    else:
        source = "none"

    return PersonnelSignal(
        grouping=grouping,
        n_rb=n_rb,
        n_te=n_te,
        n_wr=n_wr,
        n_qb=n_qb,
        n_ol=n_ol,
        confidence=confidence,
        resolved_count=resolved,
        source=source,
    )
