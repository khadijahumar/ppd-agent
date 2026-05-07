"""Module 1: Product Design Lookup.

Given a specification and dimensions, return:
- the matching HR Spec Code + Steel Grade (Z001)
- chemical composition standards (HR_Chem_Std)
- mechanical property standards (HR_Mech_Std)
- elongation standards (HR_Elongation_Std)
- thickness tolerance (HR_Thick_Toler)
- recommended Finish/Coil Temperature codes (FT_CT_Design)

All tools return plain-text strings (no markdown — Telegram-friendly).
"""
from __future__ import annotations

import pandas as pd

from .. import format as fmt
from ..data_loader import (
    load_ft_ct_design,
    load_hr_chem_std,
    load_hr_elongation_std,
    load_hr_mech_std,
    load_hr_thick_toler,
    load_z001,
)
from ..parsing import fmt_number, in_range, parse_range

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _spec_match_mask(series: pd.Series, query: str) -> pd.Series:
    """Case-insensitive substring match on a string column."""
    q = query.strip().lower()
    if not q:
        return pd.Series(False, index=series.index)
    return series.fillna("").str.lower().str.contains(q, regex=False, na=False)


def _row_thickness_match(row_thickness_range: str, thickness_mm: float | None) -> bool:
    if thickness_mm is None:
        return True
    rng = parse_range(row_thickness_range)
    return in_range(thickness_mm, rng)


def _pair_or_none(row: pd.Series, lo_col: str, hi_col: str,
                  hi_sentinel: float = 5.0) -> tuple[float | None, float | None] | None:
    """Return (lo, hi) tuple. Returns None when the row is unconstrained
    (both NaN, or lo=0 + hi above ``hi_sentinel`` — i.e. "no spec").
    """
    if lo_col not in row.index or hi_col not in row.index:
        return None
    lo = row.get(lo_col)
    hi = row.get(hi_col)
    if pd.isna(lo) and pd.isna(hi):
        return None
    lo_v = None if pd.isna(lo) else float(lo)
    hi_v = None if pd.isna(hi) else float(hi)
    lo_zero = lo_v is None or lo_v == 0.0
    hi_unbounded = hi_v is None or hi_v >= hi_sentinel
    if lo_zero and hi_unbounded:
        return None
    return (lo_v, None if hi_unbounded else hi_v)


# ---------------------------------------------------------------------------
# tool: lookup_steel_grade
# ---------------------------------------------------------------------------


def lookup_steel_grade(specification: str, thickness_mm: float | None = None,
                       limit: int = 10) -> str:
    """Return matching Steel Grade(s) and HR Spec Code from Z001.

    Args:
        specification: Standard specification string (e.g. "KI-A36",
            "EN 10025 S275JR", "API 5L X42 M"). Matched as a case-insensitive
            substring.
        thickness_mm: Optional plate thickness in millimetres. If given, only
            rows whose Thickness Range contains the value are returned.
        limit: Maximum rows returned in the table (default 10).
    """
    df = load_z001()
    mask = _spec_match_mask(df["Specification"], specification)
    sub = df[mask]
    if thickness_mm is not None:
        keep = sub.apply(lambda r: _row_thickness_match(r["Thickness Range"], thickness_mm), axis=1)
        sub = sub[keep]

    if sub.empty:
        return (
            f"Tidak ditemukan Steel Grade untuk specification='{specification}'"
            + (f", thickness={thickness_mm} mm" if thickness_mm is not None else "")
            + "."
        )

    rows = sub.head(limit)
    head = f"STEEL GRADE LOOKUP   ({len(sub)} match, showing {len(rows)})"
    table = fmt.fixed_table(
        ["Specification", "Thickness Range", "HR Spec Code", "Steel Grade"],
        [
            [r["Specification"], r["Thickness Range"], r["HR Spec Code"], r["Steel Grade"]]
            for _, r in rows.iterrows()
        ],
    )
    out = f"{head}\n{table}"
    if len(sub) > limit:
        out += f"\n  (+{len(sub) - limit} more hidden)"
    return out


# ---------------------------------------------------------------------------
# tool: lookup_chem_standard
# ---------------------------------------------------------------------------


_CHEM_ELEMENTS = [
    ("C", "%"), ("Mn", "%"), ("Si", "%"), ("P", "%"), ("S", "%"),
    ("Cu", "%"), ("Al", "%"), ("Ni", "%"), ("Cr", "%"), ("Nb", "%"),
    ("N", "%"), ("B", ""), ("Mo", "%"), ("V", "%"), ("Ti", "%"), ("Ca", "%"),
]


def lookup_chem_standard(specification: str, limit: int = 3) -> str:
    """Return chemical composition standards (min/max) for a specification."""
    df = load_hr_chem_std()
    mask = _spec_match_mask(df["Specification"], specification)
    sub = df[mask]
    if sub.empty:
        return f"Tidak ditemukan standar kimia untuk specification='{specification}'."

    blocks: list[str] = []
    for _, row in sub.head(limit).iterrows():
        head = f"CHEM STANDARD — {row['Specification']}"
        meta = f"  Dim Thickness: {row['Dim Thickness']}    Dim Width: {row['Dim Width']}"
        rows: list[list[object]] = []
        for element, unit in _CHEM_ELEMENTS:
            pair = _pair_or_none(
                row,
                f"Chemical Standard {element} Minimum",
                f"Chemical Standard {element} Maximum",
            )
            if pair is None:
                continue
            rows.append([element, fmt.fmt_range(pair[0], pair[1], decimals=4), unit])
        for label, lo_col, hi_col, unit, sentinel in [
            ("Nb+Ti+V", "Chemical Standard Nb Ti V Min", "Chemical Standard Nb Ti V Max", "%", 5.0),
            ("Cu+Ni+Cr", "Chemical Standard CuNiCr Min", "Chemical Standard CuNiCr Max", "%", 5.0),
            ("CEQ", "Chemical Standard CEQ Minimum", "Chemical Standard CEQ Maximum", "%", 5.0),
            ("PCM", "Mat Crack Parameter PCM Min", "Mat Crack Parameter PCM Max", "", 5.0),
            ("Cr+Mo+Ni+Cu", "Chemical Std Cr Mo Ni Cu Min", "Chemical Std Cr Mo Ni Cu Max", "", 5.0),
            ("Al/N", "Ratio Al/N Minimum", "Ratio Al/N Maximum", "", 50.0),
            ("Ca/S", "Ratio Ca/S Minimum", "Ratio Ca/S Maximum", "", 50.0),
            ("Ti/N", "Ratio Ti/N Minimum", "Ratio Ti/N Maximum", "", 50.0),
            ("Mn/Si", "Ratio Mn/Si Minimum", "Ratio Mn/Si Maximum", "", 50.0),
        ]:
            pair = _pair_or_none(row, lo_col, hi_col, hi_sentinel=sentinel)
            if pair is None:
                continue
            rows.append([label, fmt.fmt_range(pair[0], pair[1], decimals=4), unit])
        ceq_code = row.get("Chemical Standard CEQ Code")
        if pd.notna(ceq_code):
            rows.append(["CEQ Code", str(ceq_code), ""])
        table = fmt.fixed_table(["Element", "Range", "Unit"], rows)
        blocks.append(f"{head}\n{meta}\n{table}")

    out = fmt.join_blocks(*blocks)
    if len(sub) > limit:
        out += f"\n\n  (+{len(sub) - limit} more match hidden)"
    return out


# ---------------------------------------------------------------------------
# tool: lookup_mech_standard
# ---------------------------------------------------------------------------


def lookup_mech_standard(specification: str, thickness_mm: float | None = None,
                         limit: int = 5) -> str:
    """Return mechanical property standards (TS/YS/Charpy/HIC) for a spec."""
    df = load_hr_mech_std()
    mask = _spec_match_mask(df["Specification"], specification)
    sub = df[mask]
    if thickness_mm is not None:
        keep = sub.apply(
            lambda r: in_range(
                thickness_mm,
                (r.get("Dimension Std Thickness Min"), r.get("Dimension Std Thickness Max")),
            ),
            axis=1,
        )
        sub = sub[keep]
    if sub.empty:
        return (
            f"Tidak ditemukan standar mekanik untuk specification='{specification}'"
            + (f", thickness={thickness_mm} mm" if thickness_mm is not None else "")
            + "."
        )

    blocks: list[str] = []
    for _, r in sub.head(limit).iterrows():
        head = f"MECH STANDARD — {r['Specification']}"
        thickness_line = (
            f"  Thickness: {fmt_number(r.get('Dimension Std Thickness Min'))}"
            f" – {fmt_number(r.get('Dimension Std Thickness Max'))} mm"
        )
        rows: list[list[object]] = []

        def _add_row(label: str, lo_col: str, hi_col: str, unit: str, sentinel: float = 999.0) -> None:
            pair = _pair_or_none(r, lo_col, hi_col, hi_sentinel=sentinel)
            if pair is None:
                return
            rows.append([label, fmt.fmt_range(pair[0], pair[1], decimals=2), unit])

        _add_row("TS", "Mechanical Std Tensile Min", "Mechanical Std Tensile Max", "N/mm²")
        _add_row("YS", "Mechanical Std YS Min", "Mechanical Std YS Max", "N/mm²")
        _add_row("Charpy", "Mechanical Std Charpy Val Min", "Mechanical Std Charpy Val Max", "J")
        _add_row("YS/UTS", "YS/UTS RATIO MIN", "YS/UTS RATIO MAX", "", sentinel=99.0)
        # HIC and DWTT — skip placeholder 0–100
        for label, lo_col, hi_col, unit in [
            ("HIC CLR", "HIC CLR MIN", "HIC CLR Max", ""),
            ("HIC CSR", "HIC CSR MIN", "HIC CSR Max", ""),
            ("HIC CTR", "HIC CTR MIN", "HIC CTR Max", ""),
            ("DWTT", "DWTT Test, Indiv.Min%MinHSM", "DWTT Test, Indiv.Min%MaxHSM", "%"),
        ]:
            pair = _pair_or_none(r, lo_col, hi_col)
            if pair is None:
                continue
            lo_v, hi_v = pair
            if (lo_v in (0.0, None)) and (hi_v in (100.0, None)):
                continue  # placeholder
            rows.append([label, fmt.fmt_range(lo_v, hi_v, decimals=2), unit])

        impact_dir = r.get("Standard Direction Of Impact")
        if pd.notna(impact_dir):
            rows.append(["Impact dir", str(impact_dir), ""])

        table = fmt.fixed_table(["Property", "Range", "Unit"], rows)
        blocks.append(f"{head}\n{thickness_line}\n{table}")

    out = fmt.join_blocks(*blocks)
    if len(sub) > limit:
        out += f"\n\n  (+{len(sub) - limit} more match hidden)"
    return out


# ---------------------------------------------------------------------------
# tool: lookup_elongation_standard
# ---------------------------------------------------------------------------


def lookup_elongation_standard(specification: str, thickness_mm: float | None = None,
                               limit: int = 8) -> str:
    df = load_hr_elongation_std()
    mask = _spec_match_mask(df["Specification"], specification)
    sub = df[mask]
    if thickness_mm is not None:
        keep = sub.apply(
            lambda r: in_range(
                thickness_mm,
                (r.get("Thickness Minimum"), r.get("Thickness Maximum")),
            ),
            axis=1,
        )
        sub = sub[keep]
    if sub.empty:
        return f"Tidak ditemukan standar elongation untuk specification='{specification}'."

    head = f"ELONGATION STANDARD — '{specification}' ({len(sub)} match)"
    rows: list[list[object]] = []
    for _, r in sub.head(limit).iterrows():
        elo_min = r.get("Mech Std Elongation Min")
        elo_max = r.get("Mech Std Elongation Max")
        elo_min_v = None if pd.isna(elo_min) else float(elo_min)
        elo_max_v = None if pd.isna(elo_max) else float(elo_max)
        if elo_max_v is not None and elo_max_v >= 999:
            elo_max_v = None
        rows.append([
            r["Specification"],
            r["Thickness Range"],
            r.get("Gauge_Length", "-"),
            fmt.fmt_range(elo_min_v, elo_max_v, decimals=1, unit="%"),
        ])
    table = fmt.fixed_table(
        ["Specification", "Thickness Range", "Gauge", "ELO range"],
        rows,
    )
    out = f"{head}\n{table}"
    if len(sub) > limit:
        out += f"\n  (+{len(sub) - limit} more match hidden)"
    return out


# ---------------------------------------------------------------------------
# tool: lookup_thickness_tolerance
# ---------------------------------------------------------------------------


def lookup_thickness_tolerance(dim_thickness: str, thickness_mm: float | None = None,
                               width_mm: float | None = None, limit: int = 8) -> str:
    df = load_hr_thick_toler()
    mask = _spec_match_mask(df["Dim Thickness"], dim_thickness)
    sub = df[mask]
    if thickness_mm is not None:
        keep = sub.apply(lambda r: _row_thickness_match(r["Thickness Range"], thickness_mm), axis=1)
        sub = sub[keep]
    if width_mm is not None:
        keep = sub.apply(lambda r: in_range(width_mm, parse_range(r["Width Range"])), axis=1)
        sub = sub[keep]
    if sub.empty:
        return f"Tidak ditemukan toleransi tebal untuk dim_thickness='{dim_thickness}'."

    head = f"THICKNESS TOLERANCE — '{dim_thickness}' ({len(sub)} match)"
    rows: list[list[object]] = []
    for _, r in sub.head(limit).iterrows():
        rows.append([
            r["Dim Thickness"],
            r["Thickness Range"],
            r["Width Range"],
            fmt_number(r.get("Dimension StdThicknessTol Min")),
            fmt_number(r.get("Dimension StdThicknessTol Max")),
            r.get("Flexibility", "-"),
        ])
    table = fmt.fixed_table(
        ["Dim Thickness", "Thickness Range", "Width Range",
         "Tol Min", "Tol Max", "Flex"],
        rows,
    )
    out = f"{head}\n{table}"
    if len(sub) > limit:
        out += f"\n  (+{len(sub) - limit} more match hidden)"
    return out


# ---------------------------------------------------------------------------
# tool: lookup_ft_ct_design
# ---------------------------------------------------------------------------


def lookup_ft_ct_design(hr_spec_code: str, thickness_mm: float | None = None,
                        limit: int = 10) -> str:
    df = load_ft_ct_design()
    mask = _spec_match_mask(df["HR Spec Code"], hr_spec_code)
    sub = df[mask]
    if thickness_mm is not None:
        keep = sub.apply(lambda r: _row_thickness_match(r["Thickness Range"], thickness_mm), axis=1)
        sub = sub[keep]
    if sub.empty:
        return f"Tidak ditemukan rekomendasi FT/CT untuk hr_spec_code='{hr_spec_code}'."

    head = f"FT/CT DESIGN — '{hr_spec_code}' ({len(sub)} match)"
    rows = [
        [r["HR Spec Code"], r["Thickness Range"],
         r["Finish Temperature Code"], r["Coil Temperature Code"]]
        for _, r in sub.head(limit).iterrows()
    ]
    table = fmt.fixed_table(
        ["HR Spec Code", "Thickness Range", "Finish T Code", "Coil T Code"],
        rows,
    )
    out = f"{head}\n{table}"
    if len(sub) > limit:
        out += f"\n  (+{len(sub) - limit} more match hidden)"
    return out
