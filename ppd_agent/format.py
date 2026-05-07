"""Plain-text formatters used by every tool output.

Telegram bot messages are sent without any markdown parse_mode, so headers,
**bold**, and pipe-style markdown tables render as literal junk on the user's
screen. We keep formatting strictly to what plain text can do well:

  * UPPERCASE for section titles
  * Indentation (2 spaces) for nested items
  * Aligned columns with spaces (monospace fonts on Telegram render this OK)
  * Verdict tags like PASS / FAIL / N/A as inline plain text

Helpers here exist so every tool emits the same look-and-feel.
"""
from __future__ import annotations

from typing import Iterable, Sequence


def header(title: str) -> str:
    """Section header — UPPERCASE on its own line."""
    return title.strip().upper()


def kv(label: str, value: object, label_width: int = 14) -> str:
    """`label : value` line, left-aligned label column."""
    return f"  {label:<{label_width}} : {value}"


def bullet(text: str) -> str:
    return f"  - {text}"


def section(title: str, lines: Sequence[str]) -> str:
    """Title + indented body."""
    body = "\n".join(lines) if lines else "  (none)"
    return f"{header(title)}\n{body}"


def fixed_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    """Aligned-column table, no markdown pipes.

    Columns are left-aligned for strings, right-aligned for numeric-looking
    cells. Rendered on Telegram's monospace channels (or even default sans
    fonts) it stays readable without markdown.
    """
    if not rows:
        return "  (no rows)"
    str_rows: list[list[str]] = [[str(c) if c is not None else "-" for c in r] for r in rows]
    cols = len(headers)
    # widest cell per column (header inclusive)
    widths = [len(headers[i]) for i in range(cols)]
    for r in str_rows:
        for i in range(min(cols, len(r))):
            widths[i] = max(widths[i], len(r[i]))
    # decide per-column alignment based on content of headers + first row
    aligns: list[str] = []
    for i in range(cols):
        sample = str_rows[0][i] if i < len(str_rows[0]) else ""
        # if sample looks numeric → right-align
        try:
            float(sample.replace(",", "").rstrip("%").strip())
            aligns.append(">")
        except ValueError:
            aligns.append("<")
    # build rows
    sep = "  "
    out: list[str] = []
    out.append(sep.join(f"{h:<{widths[i]}}" for i, h in enumerate(headers)))
    out.append(sep.join("-" * widths[i] for i in range(cols)))
    for r in str_rows:
        out.append(
            sep.join(
                f"{(r[i] if i < len(r) else '-'):{aligns[i]}{widths[i]}}"
                for i in range(cols)
            )
        )
    return "\n".join(out)


def verdict_tag(ok: bool | None) -> str:
    """PASS / FAIL / N/A inline tag."""
    if ok is None:
        return "N/A"
    return "PASS" if ok else "FAIL"


def join_blocks(*blocks: str) -> str:
    """Join non-empty blocks with a blank line between."""
    return "\n\n".join(b for b in blocks if b and b.strip())


def fmt_range(low: float | None, high: float | None, decimals: int = 3,
              unit: str = "") -> str:
    """`min – max [unit]` or `≤ max` / `≥ min` for one-sided ranges."""
    suffix = f" {unit}" if unit else ""

    def _fmt(v: float | None) -> str:
        if v is None:
            return "-"
        if abs(v) >= 1000:
            return f"{v:,.{max(decimals - 2, 0)}f}".rstrip("0").rstrip(".")
        s = f"{v:.{decimals}f}"
        if "." in s:
            s = s.rstrip("0").rstrip(".")
        return s

    if low is None and high is None:
        return "-"
    if low is None:
        return f"≤ {_fmt(high)}{suffix}"
    if high is None:
        return f"≥ {_fmt(low)}{suffix}"
    return f"{_fmt(low)} – {_fmt(high)}{suffix}"


def strip_markdown(text: str) -> str:
    """Defensive scrub of any leftover markdown sigils (best-effort)."""
    out = text
    for token in ("**", "__", "###", "##", "#"):
        out = out.replace(token, "")
    # normalise pipe-table separators that survived
    out = out.replace("|", " ")
    return out


def kv_list(pairs: Iterable[tuple[str, object]], label_width: int = 14) -> str:
    """Multi-line key/value block."""
    return "\n".join(kv(k, v, label_width=label_width) for k, v in pairs)
