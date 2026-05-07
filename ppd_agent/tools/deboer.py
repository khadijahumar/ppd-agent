"""Module 3: Deboer property prediction.

Ports the empirical formulas from PPD_Assistant_web.html (lines 1325-1344)
into Python. Given a steel grade's chemical composition (min/max for each
element) plus production parameters (Thickness, CT, FT), predicts ranges
for: YS, TS, CE (Carbon Equivalent), PCM, Tnr, Ar3, Liquidus.

Also supports loading the composition from the Chemical_Design master so
the user can call ``deboer_predict_for_grade(grade, ...)`` directly.
"""
from __future__ import annotations

import math

import pandas as pd

from .. import format as fmt
from ..data_loader import load_chemical_design
from ..parsing import fmt_number

# Elements expected by every Deboer formula (lowercase keys).
DEBOER_ELEMENTS = ["C", "Mn", "Si", "P", "S", "Al", "N", "Cu", "Ni", "Cr", "Nb", "V", "Ti", "Mo", "B"]


def _g(d: dict, key: str, default: float = 0.0) -> float:
    v = d.get(key)
    if v is None:
        return default
    try:
        if v != v:  # NaN
            return default
        return float(v)
    except Exception:
        return default


def _safe_sqrt(x: float) -> float:
    if x is None or x < 0 or x != x:
        return 0.0
    return math.sqrt(x)


def deboer_calculate(
    composition_min: dict[str, float],
    composition_max: dict[str, float],
    production_min: dict[str, float],
    production_max: dict[str, float],
) -> dict[str, dict[str, float]]:
    """Run all Deboer formulas. Returns a nested dict of {prop: {min, max}}.

    Args:
        composition_min/max: dict with keys C, Mn, Si, P, S, Al, N, Cu, Ni, Cr,
            Nb, V, Ti, Mo, B (values in % or mass-fraction, same units the
            HTML used).
        production_min/max: dict with keys Thickness (mm), FT (°C), CT (°C).
    """
    cmin = {k: _g(composition_min, k) for k in DEBOER_ELEMENTS}
    cmax = {k: _g(composition_max, k) for k in DEBOER_ELEMENTS}
    pmin = {k: _g(production_min, k) for k in ["Thickness", "FT", "CT"]}
    pmax = {k: _g(production_max, k) for k in ["Thickness", "FT", "CT"]}

    ys_min = (
        275 + 310*cmin["C"] + 62*cmin["Mn"] + 85*cmin["Si"]
        + 2490*cmin["Nb"] - 1100*cmax["Ti"]
        + 97*cmin["Cu"] + 80*cmin["Ni"] + 530*cmin["V"]
        - 3*pmax["Thickness"] - 0.4*(pmax["CT"] - 580)
    )
    ys_max = (
        275 + 310*cmax["C"] + 62*cmax["Mn"] + 85*cmax["Si"]
        + 2490*cmax["Nb"] - 1100*cmin["Ti"]
        + 97*cmax["Cu"] + 80*cmax["Ni"] + 530*cmax["V"]
        - 3*pmin["Thickness"] - 0.4*(pmin["CT"] - 580)
    )

    ts_min = (
        320 + 716*cmin["C"] + 65*cmin["Mn"] + 104*cmin["Si"]
        + 1960*cmin["Nb"] - 960*cmax["Ti"]
        + 80*cmin["Cu"] + 70*cmin["Ni"] + 440*cmin["V"]
        - 2.3*pmax["Thickness"] + 0.12*(pmin["FT"] - pmax["CT"])
        - 0.2*(pmax["CT"] - 580)
    )
    ts_max = (
        320 + 716*cmax["C"] + 65*cmax["Mn"] + 104*cmax["Si"]
        + 1960*cmax["Nb"] - 960*cmin["Ti"]
        + 80*cmax["Cu"] + 70*cmax["Ni"] + 440*cmax["V"]
        - 2.3*pmin["Thickness"] + 0.12*(pmax["FT"] - pmin["CT"])
        - 0.2*(pmin["CT"] - 580)
    )

    ce_min = (
        cmin["C"] + cmin["Mn"]/6 + (cmin["Cu"] + cmin["Ni"])/15
        + (cmin["Cr"] + cmin["Mo"] + cmin["V"])/5
    )
    ce_max = (
        cmax["C"] + cmax["Mn"]/6 + (cmax["Cu"] + cmax["Ni"])/15
        + (cmax["Cr"] + cmax["Mo"] + cmax["V"])/5
    )

    pcm_min = (
        cmin["C"] + cmin["Si"]/30
        + (cmin["Mn"] + cmin["Cu"] + cmin["Cr"])/20
        + cmin["Ni"]/60 + cmin["Mo"]/15 + cmin["V"]/10 + 5*cmin["B"]
    )
    pcm_max = (
        cmax["C"] + cmax["Si"]/30
        + (cmax["Mn"] + cmax["Cu"] + cmax["Cr"])/20
        + cmax["Ni"]/60 + cmax["Mo"]/15 + cmax["V"]/10 + 5*cmax["B"]
    )

    tnr_min = (
        887 - 464*cmax["C"]
        + (6445*cmin["Nb"] - 644*_safe_sqrt(cmin["Nb"]))
        + (732*cmin["V"] - 230*_safe_sqrt(cmin["V"]))
        + 890*cmin["Ti"] + 363*cmin["Al"] - 357*cmax["Si"]
    )
    tnr_max = (
        887 - 464*cmin["C"]
        + (6445*cmax["Nb"] - 644*_safe_sqrt(cmax["Nb"]))
        + (732*cmax["V"] - 230*_safe_sqrt(cmax["V"]))
        + 890*cmax["Ti"] + 363*cmax["Al"] - 357*cmin["Si"]
    )

    ar3_min = (
        912 - 203*_safe_sqrt(cmax["C"]) - 15.2*cmax["Ni"]
        + 44.7*cmin["Si"] + 104*cmin["V"] + 31.5*cmin["Mo"]
        - 30*cmax["Mn"] - 11*cmax["Cr"] - 20*cmax["Cu"]
        + 700*cmin["P"] + 400*cmin["Al"] + 400*cmin["Ti"]
    )
    ar3_max = (
        912 - 203*_safe_sqrt(cmin["C"]) - 15.2*cmin["Ni"]
        + 44.7*cmax["Si"] + 104*cmax["V"] + 31.5*cmax["Mo"]
        - 30*cmin["Mn"] - 11*cmin["Cr"] - 20*cmin["Cu"]
        + 700*cmax["P"] + 400*cmax["Al"] + 400*cmax["Ti"]
    )

    liq_min = 1536 - (
        78*cmax["C"] + 4.9*cmax["Si"] + 7.6*cmax["Mn"]
        + 34.4*cmax["P"] + 30*cmax["S"] + 3.6*cmax["Al"]
        + 5*cmax["Cu"] + 3.1*cmax["Ni"] + 1.3*cmax["Cr"]
        + 2*cmax["Mo"] + 2*cmax["V"] + 1.8*cmax["Nb"]
    )
    liq_max = 1536 - (
        78*cmin["C"] + 4.9*cmin["Si"] + 7.6*cmin["Mn"]
        + 34.4*cmin["P"] + 30*cmin["S"] + 3.6*cmin["Al"]
        + 5*cmin["Cu"] + 3.1*cmin["Ni"] + 1.3*cmin["Cr"]
        + 2*cmin["Mo"] + 2*cmin["V"] + 1.8*cmin["Nb"]
    )

    return {
        "YS (MPa)": {"min": ys_min, "max": ys_max},
        "TS (MPa)": {"min": ts_min, "max": ts_max},
        "CE (Carbon Equivalent)": {"min": ce_min, "max": ce_max},
        "PCM": {"min": pcm_min, "max": pcm_max},
        "Tnr (°C)": {"min": tnr_min, "max": tnr_max},
        "Ar3 (°C)": {"min": ar3_min, "max": ar3_max},
        "Liquidus (°C)": {"min": liq_min, "max": liq_max},
    }


def _format_results(results: dict[str, dict[str, float]], header: str) -> str:
    rows = [
        [prop, fmt_number(v["min"], 3), fmt_number(v["max"], 3)]
        for prop, v in results.items()
    ]
    table = fmt.fixed_table(["Property", "Min", "Max"], rows)
    return f"{header}\n{table}"


def deboer_calc_text(
    composition_min: dict[str, float],
    composition_max: dict[str, float],
    production_min: dict[str, float],
    production_max: dict[str, float],
) -> str:
    """Public version that returns a plain-text result table."""
    res = deboer_calculate(composition_min, composition_max, production_min, production_max)
    return _format_results(res, "DEBOER PROPERTY PREDICTION")


# ---------------------------------------------------------------------------
# helper: fetch composition from Chemical_Design master
# ---------------------------------------------------------------------------


# Sentinel value used in the source data to mean "no constraint" (e.g.
# 9.999% B). Any element value >= this is treated as zero so it doesn't
# blow up Deboer formulas that include B, V, etc.
_SENTINEL = 5.0


def _clamp_sentinel(v: float) -> float:
    return 0.0 if (v is None or v != v or v >= _SENTINEL) else float(v)


def _design_pair(row: pd.Series, element: str) -> tuple[float, float]:
    """Return (min, max) for a single element. Sentinel '>= 5' values are
    treated as 0.0 (i.e. "no upper bound") so empirical formulas don't blow up.
    """
    lo_col = f"Chemical Design {element} Minimum"
    hi_col = f"Chemical Design {element} Maximum"
    lo = row.get(lo_col); hi = row.get(hi_col)
    lo_v = 0.0 if pd.isna(lo) else float(lo)
    hi_v = 0.0 if pd.isna(hi) else float(hi)
    return _clamp_sentinel(lo_v), _clamp_sentinel(hi_v)


def deboer_get_grade(steel_grade: str) -> dict | None:
    """Look up the Chemical_Design row for a steel grade. Returns None if missing."""
    df = load_chemical_design()
    sub = df[df["Steel Grade"].str.upper() == steel_grade.strip().upper()]
    if sub.empty:
        # substring fallback
        sub = df[df["Steel Grade"].str.contains(steel_grade, case=False, na=False, regex=False)]
    if sub.empty:
        return None
    row = sub.iloc[0]
    cmin: dict[str, float] = {}
    cmax: dict[str, float] = {}
    for el in DEBOER_ELEMENTS:
        lo, hi = _design_pair(row, el)
        cmin[el] = lo; cmax[el] = hi
    return {
        "matched_grade": str(row["Steel Grade"]),
        "deformation_group": float(row.get("Deformation Group")) if pd.notna(row.get("Deformation Group")) else None,
        "composition_min": cmin,
        "composition_max": cmax,
    }


def deboer_predict_for_grade(
    steel_grade: str,
    thickness_min_mm: float,
    thickness_max_mm: float,
    ct_min_c: float,
    ct_max_c: float,
    ft_min_c: float,
    ft_max_c: float,
) -> str:
    """End-to-end: load grade composition + apply Deboer + return a readable report."""
    info = deboer_get_grade(steel_grade)
    if info is None:
        return f"Steel Grade '{steel_grade}' tidak ditemukan di Chemical_Design."

    res = deboer_calculate(
        info["composition_min"], info["composition_max"],
        {"Thickness": thickness_min_mm, "CT": ct_min_c, "FT": ft_min_c},
        {"Thickness": thickness_max_mm, "CT": ct_max_c, "FT": ft_max_c},
    )

    head = (
        f"DEBOER PREDICTION — Steel Grade {info['matched_grade']}\n"
        f"  Production: thickness {thickness_min_mm}–{thickness_max_mm} mm, "
        f"CT {ct_min_c}–{ct_max_c} °C, FT {ft_min_c}–{ft_max_c} °C"
    )
    comp_rows: list[list[object]] = []
    for el in DEBOER_ELEMENTS:
        lo = info["composition_min"][el]
        hi = info["composition_max"][el]
        if lo or hi:
            comp_rows.append([el, fmt_number(lo), fmt_number(hi)])
    comp_block = ""
    if comp_rows:
        comp_block = (
            "COMPOSITION (design min – max)\n"
            + fmt.fixed_table(["Element", "Min", "Max"], comp_rows)
        )
    pred_rows = [
        [prop, fmt_number(v["min"], 3), fmt_number(v["max"], 3)]
        for prop, v in res.items()
    ]
    pred_block = "PREDICTED PROPERTIES\n" + fmt.fixed_table(
        ["Property", "Min", "Max"], pred_rows,
    )
    return fmt.join_blocks(head, comp_block, pred_block)
