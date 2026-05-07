"""Module 1: Product Design Lookup.

Given a specification and dimensions, return:
- the matching HR Spec Code + Steel Grade (Z001)
- chemical composition standards (HR_Chem_Std)
- mechanical property standards (HR_Mech_Std)
- elongation standards (HR_Elongation_Std)
- thickness tolerance (HR_Thick_Toler)
- recommended Finish/Coil Temperature codes (FT_CT_Design)

All tools return human-readable markdown strings the agent can pass straight
back to the user.
"""
from __future__ import annotations

import pandas as pd

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


def _format_chem_pair(row: pd.Series, element: str, label: str | None = None,
                     unit: str = "%") -> str | None:
    """Render '<min> – <max> %' for the C/Mn/... pair if either bound is present."""
    label = label or element
    min_col = f"Chemical Standard {element} Minimum"
    max_col = f"Chemical Standard {element} Maximum"
    if min_col not in row.index or max_col not in row.index:
        return None
    lo = row.get(min_col)
    hi = row.get(max_col)
    if pd.isna(lo) and pd.isna(hi):
        return None
    lo_s = fmt_number(None if pd.isna(lo) else float(lo))
    hi_s = fmt_number(None if pd.isna(hi) else float(hi))
    return f"  - **{label}**: {lo_s} – {hi_s} {unit}"


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
    lines = [
        f"### Steel Grade Lookup ({len(sub)} match, menampilkan {len(rows)})",
        "",
        "| Specification | Thickness Range | HR Spec Code | Steel Grade |",
        "|---|---|---|---|",
    ]
    for _, r in rows.iterrows():
        lines.append(
            f"| {r['Specification']} | {r['Thickness Range']} | "
            f"{r['HR Spec Code']} | {r['Steel Grade']} |"
        )
    return "\n".join(lines)


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

    out: list[str] = []
    for i, (_, row) in enumerate(sub.head(limit).iterrows()):
        out.append(f"### Chem Standard – {row['Specification']}")
        out.append(f"  Dim Thickness: {row['Dim Thickness']}  |  Dim Width: {row['Dim Width']}")
        out.append("**Komposisi (min – max):**")
        for element, unit in _CHEM_ELEMENTS:
            line = _format_chem_pair(row, element, unit=unit)
            if line:
                out.append(line)
        # group sums + ratios + CEQ + PCM
        for label, lo_col, hi_col, unit in [
            ("Nb+Ti+V", "Chemical Standard Nb Ti V Min", "Chemical Standard Nb Ti V Max", "%"),
            ("Cu+Ni+Cr", "Chemical Standard CuNiCr Min", "Chemical Standard CuNiCr Max", "%"),
            ("CEQ", "Chemical Standard CEQ Minimum", "Chemical Standard CEQ Maximum", "%"),
            ("PCM", "Mat Crack Parameter PCM Min", "Mat Crack Parameter PCM Max", ""),
            ("Cr+Mo+Ni+Cu", "Chemical Std Cr Mo Ni Cu Min", "Chemical Std Cr Mo Ni Cu Max", ""),
            ("Al/N", "Ratio Al/N Minimum", "Ratio Al/N Maximum", ""),
            ("Ca/S", "Ratio Ca/S Minimum", "Ratio Ca/S Maximum", ""),
            ("Ti/N", "Ratio Ti/N Minimum", "Ratio Ti/N Maximum", ""),
            ("Mn/Si", "Ratio Mn/Si Minimum", "Ratio Mn/Si Maximum", ""),
        ]:
            if lo_col in row.index and hi_col in row.index:
                lo = row.get(lo_col); hi = row.get(hi_col)
                if pd.notna(lo) or pd.notna(hi):
                    lo_s = fmt_number(None if pd.isna(lo) else float(lo))
                    hi_s = fmt_number(None if pd.isna(hi) else float(hi))
                    out.append(f"  - **{label}**: {lo_s} – {hi_s} {unit}".rstrip())
        ceq_code = row.get("Chemical Standard CEQ Code")
        if pd.notna(ceq_code):
            out.append(f"  - CEQ Code: {ceq_code}")
        if i < min(limit, len(sub)) - 1:
            out.append("")
    if len(sub) > limit:
        out.append(f"\n_(+{len(sub) - limit} hasil lain dipotong)_")
    return "\n".join(out)


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

    out: list[str] = [f"### Mech Standard – '{specification}'  ({len(sub)} match, top {min(limit, len(sub))})"]
    for _, r in sub.head(limit).iterrows():
        out.append("")
        out.append(f"**{r['Specification']}**  thickness "
                   f"{fmt_number(r.get('Dimension Std Thickness Min'))} – "
                   f"{fmt_number(r.get('Dimension Std Thickness Max'))} mm")
        out.append(f"  - TS  : {fmt_number(r.get('Mechanical Std Tensile Min'))} – "
                   f"{fmt_number(r.get('Mechanical Std Tensile Max'))} N/mm²")
        out.append(f"  - YS  : {fmt_number(r.get('Mechanical Std YS Min'))} – "
                   f"{fmt_number(r.get('Mechanical Std YS Max'))} N/mm²")
        if pd.notna(r.get("Mechanical Std Charpy Val Min")) or pd.notna(r.get("Mechanical Std Charpy Val Max")):
            out.append(f"  - Charpy: {fmt_number(r.get('Mechanical Std Charpy Val Min'))} – "
                       f"{fmt_number(r.get('Mechanical Std Charpy Val Max'))} J  "
                       f"(dir: {r.get('Standard Direction Of Impact', '-')})")
        ratio_min = r.get("YS/UTS RATIO MIN"); ratio_max = r.get("YS/UTS RATIO MAX")
        if pd.notna(ratio_min) or pd.notna(ratio_max):
            out.append(f"  - YS/UTS Ratio: {fmt_number(ratio_min)} – {fmt_number(ratio_max)}")
        for label, lo_col, hi_col in [
            ("HIC CLR", "HIC CLR MIN", "HIC CLR Max"),
            ("HIC CSR", "HIC CSR MIN", "HIC CSR Max"),
            ("HIC CTR", "HIC CTR MIN", "HIC CTR Max"),
            ("DWTT", "DWTT Test, Indiv.Min%MinHSM", "DWTT Test, Indiv.Min%MaxHSM"),
        ]:
            lo = r.get(lo_col); hi = r.get(hi_col)
            if pd.notna(lo) or pd.notna(hi):
                # Skip noisy 0–100 placeholders
                lo_v = float(lo) if pd.notna(lo) else None
                hi_v = float(hi) if pd.notna(hi) else None
                is_placeholder = (lo_v in (0.0, None)) and (hi_v in (100.0, None))
                if not is_placeholder:
                    out.append(f"  - {label}: {fmt_number(lo_v)} – {fmt_number(hi_v)}")
    if len(sub) > limit:
        out.append(f"\n_(+{len(sub) - limit} hasil lain dipotong)_")
    return "\n".join(out)


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

    lines = [f"### Elongation Standard – '{specification}' ({len(sub)} match)",
             "",
             "| Specification | Thickness Range | Gauge Length | ELO min | ELO max |",
             "|---|---|---|---|---|"]
    for _, r in sub.head(limit).iterrows():
        lines.append(
            f"| {r['Specification']} | {r['Thickness Range']} | {r.get('Gauge_Length', '-')} | "
            f"{fmt_number(r.get('Mech Std Elongation Min'))} % | "
            f"{fmt_number(r.get('Mech Std Elongation Max'))} % |"
        )
    if len(sub) > limit:
        lines.append(f"\n_(+{len(sub) - limit} hasil lain dipotong)_")
    return "\n".join(lines)


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

    lines = [
        f"### Thickness Tolerance – '{dim_thickness}' ({len(sub)} match)",
        "",
        "| Dim Thickness | Thickness Range | Width Range | Tol Min (mm) | Tol Max (mm) | Flex |",
        "|---|---|---|---|---|---|",
    ]
    for _, r in sub.head(limit).iterrows():
        lines.append(
            f"| {r['Dim Thickness']} | {r['Thickness Range']} | {r['Width Range']} | "
            f"{fmt_number(r.get('Dimension StdThicknessTol Min'))} | "
            f"{fmt_number(r.get('Dimension StdThicknessTol Max'))} | {r.get('Flexibility', '-')} |"
        )
    if len(sub) > limit:
        lines.append(f"\n_(+{len(sub) - limit} hasil lain dipotong)_")
    return "\n".join(lines)


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

    lines = [
        f"### FT/CT Design – '{hr_spec_code}' ({len(sub)} match)",
        "",
        "| HR Spec Code | Thickness Range | Finish Temp Code | Coil Temp Code |",
        "|---|---|---|---|",
    ]
    for _, r in sub.head(limit).iterrows():
        lines.append(
            f"| {r['HR Spec Code']} | {r['Thickness Range']} | "
            f"{r['Finish Temperature Code']} | {r['Coil Temperature Code']} |"
        )
    if len(sub) > limit:
        lines.append(f"\n_(+{len(sub) - limit} hasil lain dipotong)_")
    return "\n".join(lines)
