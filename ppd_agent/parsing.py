"""Number / range parsing utilities.

The source xlsx files use Indonesian/European number formatting (comma as
decimal separator, dot as thousand separator) and many "soft" conventions
like leading "<", ">", "<=", ">=", trailing units ("%", "mm", "N/mm2", "J"),
and ranges ("0,000 - 2,999"). These helpers normalise them into plain
floats and (min, max) tuples.

Behaviour mirrors `parseToNumber` and `parseThicknessRange` from the
original PPD_Assistant_web.html so results stay consistent.
"""
from __future__ import annotations

import re

_UNIT_RE = re.compile(r"\s*(%|mm|N/mm2|N/mm²|MPa|J|°C|C|kg|g|m)\s*$", re.IGNORECASE)


def parse_number(value, default: float | None = None) -> float | None:
    """Parse a single numeric scalar tolerating the messy xlsx formats."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        # Filter out NaN cheaply; pandas may pass float('nan').
        try:
            if value != value:  # NaN check
                return default
        except Exception:
            pass
        return float(value)

    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "-"}:
        return default

    # "10,000 - 12,999" -> take left side.
    if " - " in s:
        s = s.split(" - ", 1)[0]

    # leading comparators
    for prefix in ("<= ", ">= ", "< ", "> "):
        if s.startswith(prefix):
            s = s[len(prefix):]
            break

    # strip trailing unit
    s = _UNIT_RE.sub("", s)

    # remove anything that's not digit, sign, dot, or comma
    cleaned = re.sub(r"\s+", "", s)
    cleaned = re.sub(r"[^0-9.,+\-]", "", cleaned)
    cleaned = re.sub(r"(?!^)[+\-]", "", cleaned)
    if not cleaned or cleaned in {"+", "-", "+.", "-.", ".", ","}:
        return default

    last_comma = cleaned.rfind(",")
    last_dot = cleaned.rfind(".")
    if last_comma != -1 and last_dot != -1:
        if last_comma > last_dot:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif last_comma != -1:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")

    try:
        n = float(cleaned)
    except ValueError:
        return default
    if n != n:  # NaN
        return default
    return n


def parse_range(value, default: tuple[float | None, float | None] | None = None
                ) -> tuple[float | None, float | None] | None:
    """Parse strings like '10,000 - 12,999' or '7,000 - < 10,000' into (min, max)."""
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default

    if " - " in s:
        left, right = s.split(" - ", 1)
        lo = parse_number(left)
        right_stripped = right.strip()
        # exclusive upper bound: "< 10,000" -> 9,999.999
        exclusive = right_stripped.startswith("<") and not right_stripped.startswith("<=")
        hi = parse_number(right_stripped)
        if exclusive and hi is not None:
            hi = hi - 0.001
        return (lo, hi)

    # bare number -> exact match with small tolerance
    n = parse_number(s)
    if n is None:
        return default
    return (n - 0.001, n + 0.001)


def in_range(value: float | None, rng: tuple[float | None, float | None] | None,
             *, inclusive: bool = True) -> bool:
    """Return True if `value` satisfies the (lo, hi) range. Open-ended sides count as unbounded."""
    if value is None or rng is None:
        return False
    lo, hi = rng
    if lo is not None:
        if inclusive:
            if value < lo:
                return False
        else:
            if value <= lo:
                return False
    if hi is not None:
        if inclusive:
            if value > hi:
                return False
        else:
            if value >= hi:
                return False
    return True


def fmt_number(value: float | None, decimals: int = 4) -> str:
    """Compact human-readable number formatting used in tool outputs."""
    if value is None:
        return "-"
    try:
        if abs(value) >= 1000:
            s = f"{value:,.{max(decimals - 2, 0)}f}"
        else:
            s = f"{value:.{decimals}f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s
    except Exception:
        return str(value)
