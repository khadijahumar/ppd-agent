"""Module 4: Compliance check (KILLER FEATURE).

Cross-references actual coil data from the 290k production dataset with
chemical and mechanical standards (HR_Chem_Std, HR_Mech_Std) to produce a
pass/fail report per element / per property.

Public API:
    check_chem_compliance(coil_id, specification=None)
    check_mech_compliance(coil_id, specification=None)
    full_compliance_report(coil_id, specification=None)

If `specification` is omitted, the coil's own ``Spec Code`` is used.
"""
from __future__ import annotations

import pandas as pd

from ..data_loader import load_hr_chem_std, load_hr_mech_std, load_produksi_hrc
from ..parsing import fmt_number

# Map production column → HR_Chem_Std min/max column suffix.
# Production data uses uppercase column names; standards use Title-case.
CHEM_MAP: list[tuple[str, str, str]] = [
    # (production_col, std_min_col, std_max_col)
    ("C",  "Chemical Standard C Minimum",  "Chemical Standard C Maximum"),
    ("MN", "Chemical Standard Mn Minimum", "Chemical Standard Mn Maximum"),
    ("SI", "Chemical Standard Si Minimum", "Chemical Standard Si Maximum"),
    ("P",  "Chemical Standard P Minimum",  "Chemical Standard P Maximum"),
    ("S",  "Chemical Standard S Minimum",  "Chemical Standard S Maximum"),
    ("CU", "Chemical Standard Cu Minimum", "Chemical Standard Cu Maximum"),
    ("AL", "Chemical Standard Al Minimum", "Chemical Standard Al Maximum"),
    ("NI", "Chemical Standard Ni Minimum", "Chemical Standard Ni Maximum"),
    ("CR", "Chemical Standard Cr Minimum", "Chemical Standard Cr Maximum"),
    ("NB", "Chemical Standard Nb Minimum", "Chemical Standard Nb Maximum"),
    ("N",  "Chemical Standard N Minimum",  "Chemical Standard N Maximum"),
    ("B",  "Chemical Standard B Minimum",  "Chemical Standard B Maximum"),
    ("MO", "Chemical Standard Mo Minimum", "Chemical Standard Mo Maximum"),
    ("V",  "Chemical Standard V Minimum",  "Chemical Standard V Maximum"),
    ("TI", "Chemical Standard Ti Minimum", "Chemical Standard Ti Maximum"),
    ("CEQ","Chemical Standard CEQ Minimum","Chemical Standard CEQ Maximum"),
    ("PCM","Mat Crack Parameter PCM Min", "Mat Crack Parameter PCM Max"),
]

MECH_MAP: list[tuple[str, str, str, str]] = [
    # (production_col, std_min_col, std_max_col, unit)
    ("YS",  "Mechanical Std YS Min",      "Mechanical Std YS Max",      "N/mm²"),
    ("TS",  "Mechanical Std Tensile Min", "Mechanical Std Tensile Max", "N/mm²"),
    ("Impact", "Mechanical Std Charpy Val Min", "Mechanical Std Charpy Val Max", "J"),
]

# Sentinel: standard rows often use 0/9.999/100 to mean "no constraint".
_SENTINEL_LOW = 0.0
_SENTINEL_HIGH_VALUES = {9.999, 99.99, 999.0}


def _is_unbounded(low: float | None, high: float | None) -> tuple[bool, bool]:
    """Detect placeholder bounds. Returns (low_unbounded, high_unbounded)."""
    lo_unb = (low is None) or (low != low) or (low == _SENTINEL_LOW)
    hi_unb = (high is None) or (high != high) or (high in _SENTINEL_HIGH_VALUES) or (high >= 99.0)
    return lo_unb, hi_unb


def _find_coil(coil_id: str) -> pd.Series | None:
    df = load_produksi_hrc()
    sub = df[df["Coil ID"].fillna("").str.upper() == coil_id.strip().upper()]
    if sub.empty:
        return None
    return sub.iloc[0]


def _find_chem_std(specification: str) -> pd.Series | None:
    df = load_hr_chem_std()
    spec = specification.strip()
    sub = df[df["Specification"].fillna("").str.lower() == spec.lower()]
    if sub.empty:
        sub = df[df["Specification"].fillna("").str.contains(spec, case=False, na=False, regex=False)]
    if sub.empty:
        # try simplified: drop common qualifiers
        simplified = (
            spec.replace("MS EN", "EN").replace("BS EN", "EN")
                .replace("+AR", "").replace(":2011", "").strip()
        )
        if simplified != spec:
            sub = df[df["Specification"].fillna("").str.contains(simplified, case=False, na=False, regex=False)]
    if sub.empty:
        return None
    return sub.iloc[0]


def _find_mech_std(specification: str, thickness_mm: float | None = None) -> pd.Series | None:
    df = load_hr_mech_std()
    spec = specification.strip()
    sub = df[df["Specification"].fillna("").str.lower() == spec.lower()]
    if sub.empty:
        sub = df[df["Specification"].fillna("").str.contains(spec, case=False, na=False, regex=False)]
    if sub.empty:
        simplified = (
            spec.replace("MS EN", "EN").replace("BS EN", "EN")
                .replace("+AR", "").replace(":2011", "").strip()
        )
        if simplified != spec:
            sub = df[df["Specification"].fillna("").str.contains(simplified, case=False, na=False, regex=False)]
    if sub.empty:
        return None

    if thickness_mm is not None and len(sub) > 1:
        sub = sub[
            (sub["Dimension Std Thickness Min"].fillna(0) <= thickness_mm)
            & (sub["Dimension Std Thickness Max"].fillna(99999) >= thickness_mm)
        ]
        if sub.empty:
            return None
    return sub.iloc[0]


# ---------------------------------------------------------------------------
# chemical compliance
# ---------------------------------------------------------------------------


def check_chem_compliance(coil_id: str, specification: str | None = None) -> str:
    coil = _find_coil(coil_id)
    if coil is None:
        return f"Coil '{coil_id}' tidak ditemukan."

    spec_used = specification or coil.get("Spec Code", "")
    if not spec_used:
        return f"Coil {coil_id} tidak punya Spec Code dan specification tidak diberikan."

    std = _find_chem_std(str(spec_used))
    if std is None:
        return (f"Tidak menemukan standar kimia untuk specification='{spec_used}' "
                f"(coil {coil_id}).")

    n_pass = 0; n_fail = 0; n_info = 0
    rows = []
    for prod_col, lo_col, hi_col in CHEM_MAP:
        actual = coil.get(prod_col)
        std_lo = std.get(lo_col); std_hi = std.get(hi_col)
        if pd.isna(actual):
            rows.append((prod_col, None, std_lo, std_hi, "N/A"))
            n_info += 1
            continue
        actual_v = float(actual)
        lo_v = None if pd.isna(std_lo) else float(std_lo)
        hi_v = None if pd.isna(std_hi) else float(std_hi)
        lo_unb, hi_unb = _is_unbounded(lo_v, hi_v)
        ok_lo = lo_unb or (actual_v >= lo_v)
        ok_hi = hi_unb or (actual_v <= hi_v)
        verdict = "PASS" if (ok_lo and ok_hi) else "FAIL"
        if verdict == "PASS":
            n_pass += 1
        else:
            n_fail += 1
        rows.append((prod_col, actual_v, lo_v if not lo_unb else None, hi_v if not hi_unb else None, verdict))

    overall = "FAIL" if n_fail > 0 else "PASS"
    out = [
        f"### Chemical Compliance — Coil {coil_id}",
        f"Spec used: **{spec_used}**  (matched std: '{std['Specification']}')",
        f"Result: **{overall}**  ({n_pass} pass, {n_fail} fail, {n_info} N/A)",
        "",
        "| Element | Actual | Std Min | Std Max | Verdict |",
        "|---|---|---|---|---|",
    ]
    for prod_col, actual_v, lo_v, hi_v, verdict in rows:
        a_s = "-" if actual_v is None else fmt_number(actual_v, 4)
        lo_s = "-" if lo_v is None else fmt_number(lo_v, 4)
        hi_s = "-" if hi_v is None else fmt_number(hi_v, 4)
        flag = "✅" if verdict == "PASS" else ("❌" if verdict == "FAIL" else "ℹ️")
        out.append(f"| {prod_col} | {a_s} | {lo_s} | {hi_s} | {flag} {verdict} |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# mechanical compliance
# ---------------------------------------------------------------------------


def check_mech_compliance(coil_id: str, specification: str | None = None) -> str:
    coil = _find_coil(coil_id)
    if coil is None:
        return f"Coil '{coil_id}' tidak ditemukan."

    spec_used = specification or coil.get("Spec Code", "")
    if not spec_used:
        return f"Coil {coil_id} tidak punya Spec Code dan specification tidak diberikan."

    thickness = coil.get("TBL_ACT")
    thickness_v = None if pd.isna(thickness) else float(thickness)
    std = _find_mech_std(str(spec_used), thickness_v)
    if std is None:
        return (f"Tidak menemukan standar mekanik untuk specification='{spec_used}', "
                f"thickness={thickness_v} mm.")

    n_pass = 0; n_fail = 0; n_info = 0
    rows = []
    for prod_col, lo_col, hi_col, unit in MECH_MAP:
        actual = coil.get(prod_col)
        std_lo = std.get(lo_col); std_hi = std.get(hi_col)
        if pd.isna(actual):
            rows.append((prod_col, None, std_lo, std_hi, unit, "N/A"))
            n_info += 1
            continue
        actual_v = float(actual)
        lo_v = None if pd.isna(std_lo) else float(std_lo)
        hi_v = None if pd.isna(std_hi) else float(std_hi)
        lo_unb, hi_unb = _is_unbounded(lo_v, hi_v)
        ok_lo = lo_unb or (actual_v >= lo_v)
        ok_hi = hi_unb or (actual_v <= hi_v)
        verdict = "PASS" if (ok_lo and ok_hi) else "FAIL"
        if verdict == "PASS":
            n_pass += 1
        else:
            n_fail += 1
        rows.append((prod_col, actual_v, lo_v if not lo_unb else None, hi_v if not hi_unb else None, unit, verdict))

    # ELO has its own dedicated standard (HR_Elongation_Std), not in HR_Mech_Std
    # — skipped here for brevity. ELO compliance can be added in a follow-up.

    overall = "FAIL" if n_fail > 0 else ("PASS" if n_pass > 0 else "INSUFFICIENT_DATA")
    out = [
        f"### Mechanical Compliance — Coil {coil_id}",
        f"Spec used: **{spec_used}**  (matched std: '{std['Specification']}', "
        f"thickness range {fmt_number(std.get('Dimension Std Thickness Min'))}-"
        f"{fmt_number(std.get('Dimension Std Thickness Max'))} mm)",
        f"Coil thickness (TBL_ACT): {fmt_number(thickness_v)} mm",
        f"Result: **{overall}**  ({n_pass} pass, {n_fail} fail, {n_info} N/A)",
        "",
        "| Property | Actual | Std Min | Std Max | Verdict |",
        "|---|---|---|---|---|",
    ]
    for prod_col, actual_v, lo_v, hi_v, unit, verdict in rows:
        a_s = "-" if actual_v is None else f"{fmt_number(actual_v, 3)} {unit}"
        lo_s = "-" if lo_v is None else f"{fmt_number(lo_v, 3)} {unit}"
        hi_s = "-" if hi_v is None else f"{fmt_number(hi_v, 3)} {unit}"
        flag = "✅" if verdict == "PASS" else ("❌" if verdict == "FAIL" else "ℹ️")
        out.append(f"| {prod_col} | {a_s} | {lo_s} | {hi_s} | {flag} {verdict} |")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# combined report
# ---------------------------------------------------------------------------


def full_compliance_report(coil_id: str, specification: str | None = None) -> str:
    chem = check_chem_compliance(coil_id, specification)
    mech = check_mech_compliance(coil_id, specification)
    return chem + "\n\n" + mech
