"""Module 5: Feasibility analysis.

Connects four data sources into one engineering-grade verdict:

1. ``Chemical_Design`` — design composition envelope of a Steel Grade.
2. ``HR_Chem_Std``     — chemical requirements of a target Specification.
3. ``HR_Mech_Std``     — mechanical requirements of a target Specification.
4. Deboer formulas    — predict YS / TS / CE / PCM / Tnr / Ar3 / Liquidus
                        from composition + production parameters.
5. ``Produksi_2021_HRC`` — historical production of grade & spec.

The flagship tool is :func:`feasibility_analysis(steel_grade, specification)`
which answers "can we use Steel Grade X to fulfil Specification Y, even if
we have never produced it before?".

Verdict is binary: **FEASIBLE** or **NOT FEASIBLE**.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .. import format as fmt
from ..aliases import (
    GradeMatch,
    SpecMatch,
    get_chemical_design_row,
    resolve_specification,
    resolve_steel_grade,
)
from ..data_loader import (
    load_chemical_design,
    load_hr_chem_std,
    load_hr_elongation_std,
    load_hr_mech_std,
    load_produksi_hrc,
)
from ..ft_ct_codes import CT_CODES, FT_CODES, TempCode, list_ct_codes, list_ft_codes
from .deboer import DEBOER_ELEMENTS, _design_pair, deboer_calculate

# ---------------------------------------------------------------------------
# constants
# ---------------------------------------------------------------------------

# Logical name → ("Chemical Design X" col root, "Chemical Standard X" col root).
_CHEM_ELEMENT_MAP: list[tuple[str, str, str]] = [
    ("C",  "Chemical Design C",  "Chemical Standard C"),
    ("Mn", "Chemical Design Mn", "Chemical Standard Mn"),
    ("Si", "Chemical Design Si", "Chemical Standard Si"),
    ("P",  "Chemical Design P",  "Chemical Standard P"),
    ("S",  "Chemical Design S",  "Chemical Standard S"),
    ("Cu", "Chemical Design Cu", "Chemical Standard Cu"),
    ("Al", "Chemical Design Al", "Chemical Standard Al"),
    ("Ni", "Chemical Design Ni", "Chemical Standard Ni"),
    ("Cr", "Chemical Design Cr", "Chemical Standard Cr"),
    ("Nb", "Chemical Design Nb", "Chemical Standard Nb"),
    ("N",  "Chemical Design N",  "Chemical Standard N"),
    ("B",  "Chemical Design B",  "Chemical Standard B"),
    ("Mo", "Chemical Design Mo", "Chemical Standard Mo"),
    ("V",  "Chemical Design V",  "Chemical Standard V"),
    ("Ti", "Chemical Design Ti", "Chemical Standard Ti"),
    ("Ca", "Chemical Design Ca", "Chemical Standard Ca"),
    ("CEQ", "Chemical Design CEQ", "Chemical Standard CEQ"),
    ("PCM", "Dsn MatCrack Parameter PCM", "Mat Crack Parameter PCM"),
]

# Standard thickness sweep (mm) when user gives no thickness hint.
_DEFAULT_THICKNESS_SWEEP_MM = [3.0, 4.5, 6.0, 8.0, 10.0, 12.5, 16.0, 20.0]

# Sentinel: a value at or above this is treated as "no constraint".
_STD_SENTINEL = 5.0


# ---------------------------------------------------------------------------
# data classes
# ---------------------------------------------------------------------------


@dataclass
class ElementCheck:
    element: str
    design_min: float | None
    design_max: float | None
    std_min: float | None
    std_max: float | None
    verdict: str   # PASS, FAIL, N/A
    reason: str = ""


@dataclass
class MechCheck:
    property: str
    predicted_min: float | None
    predicted_max: float | None
    std_min: float | None
    std_max: float | None
    unit: str
    verdict: str
    reason: str = ""


@dataclass
class ChemReport:
    rows: list[ElementCheck]
    verdict: str
    n_pass: int
    n_fail: int
    n_na: int


@dataclass
class MechReport:
    rows: list[MechCheck]
    verdict: str
    thickness_mm: float
    ft: TempCode
    ct: TempCode
    ce_min: float | None = None
    ce_max: float | None = None
    pcm_min: float | None = None
    pcm_max: float | None = None


@dataclass
class ParamCombo:
    thickness_mm: float
    ft: TempCode
    ct: TempCode
    score: float
    mech: MechReport


# ---------------------------------------------------------------------------
# resolution
# ---------------------------------------------------------------------------


def _format_grade_options(matches: list[GradeMatch]) -> str:
    return ", ".join(m.canonical for m in matches[:10])


def _format_spec_options(matches: list[SpecMatch]) -> str:
    return "\n".join(f"  - {m.canonical}" for m in matches[:10])


def _resolve_grade_or_message(query: str) -> tuple[str | None, str]:
    matches = resolve_steel_grade(query)
    if not matches:
        return None, f"Steel Grade '{query}' tidak ditemukan di Chemical_Design."
    if len(matches) > 1 and matches[0].matched_via == "substring":
        return None, (
            f"Steel Grade '{query}' ambigu. Kandidat: "
            f"{_format_grade_options(matches)}. Sebutkan kode lengkap."
        )
    return matches[0].canonical, ""


def _resolve_spec_or_message(query: str) -> tuple[str | None, str]:
    matches = resolve_specification(query)
    if not matches:
        return None, f"Specification '{query}' tidak ditemukan di HR_Chem_Std atau HR_Mech_Std."
    if len(matches) > 1 and matches[0].matched_via != "exact":
        return None, (
            f"Specification '{query}' ambigu. Pilih salah satu:\n"
            f"{_format_spec_options(matches)}\n"
            f"Lalu ulangi pertanyaan dengan nama lengkap."
        )
    return matches[0].canonical, ""


# ---------------------------------------------------------------------------
# helpers — chem
# ---------------------------------------------------------------------------


def _spec_chem_row(spec: str) -> Optional[pd.Series]:
    df = load_hr_chem_std()
    sub = df[df["Specification"].astype(str) == spec]
    if sub.empty:
        return None
    return sub.iloc[0]


def _val_or_none(row: pd.Series, col: str) -> float | None:
    if col not in row.index:
        return None
    v = row[col]
    if pd.isna(v):
        return None
    return float(v)


def _is_unbounded_std(low: float | None, high: float | None) -> tuple[bool, bool]:
    lo_unb = low is None or low == 0.0
    hi_unb = high is None or (high is not None and high >= _STD_SENTINEL)
    return lo_unb, hi_unb


def _design_unbounded(low: float | None, high: float | None) -> bool:
    lo_zero = low is None or low == 0.0
    hi_zero_or_sentinel = high is None or high == 0.0 or high >= _STD_SENTINEL
    return lo_zero and hi_zero_or_sentinel


def _check_one_element(
    element: str,
    design_lo: float | None, design_hi: float | None,
    std_lo: float | None, std_hi: float | None,
) -> ElementCheck:
    lo_unb, hi_unb = _is_unbounded_std(std_lo, std_hi)
    if lo_unb and hi_unb:
        return ElementCheck(
            element=element,
            design_min=design_lo, design_max=design_hi,
            std_min=None, std_max=None,
            verdict="N/A", reason="standar tidak menetapkan batas",
        )
    if _design_unbounded(design_lo, design_hi):
        return ElementCheck(
            element=element,
            design_min=design_lo, design_max=design_hi,
            std_min=std_lo if not lo_unb else None,
            std_max=std_hi if not hi_unb else None,
            verdict="N/A", reason="design tidak menetapkan batas",
        )

    fail_upper = (not hi_unb) and (design_hi is not None) and design_hi > std_hi
    fail_lower = (not lo_unb) and (design_lo is not None) and design_lo < std_lo

    if fail_upper or fail_lower:
        why: list[str] = []
        if fail_upper:
            why.append(f"design max {design_hi} > std max {std_hi}")
        if fail_lower:
            why.append(f"design min {design_lo} < std min {std_lo}")
        return ElementCheck(
            element=element,
            design_min=design_lo, design_max=design_hi,
            std_min=std_lo if not lo_unb else None,
            std_max=std_hi if not hi_unb else None,
            verdict="FAIL", reason="; ".join(why),
        )
    return ElementCheck(
        element=element,
        design_min=design_lo, design_max=design_hi,
        std_min=std_lo if not lo_unb else None,
        std_max=std_hi if not hi_unb else None,
        verdict="PASS",
    )


def check_chemical_compatibility(
    grade_row: pd.Series,
    spec_row: pd.Series,
) -> ChemReport:
    rows: list[ElementCheck] = []
    for element, design_root, std_root in _CHEM_ELEMENT_MAP:
        if element in {"CEQ", "PCM"}:
            d_lo = _val_or_none(grade_row, f"{design_root} Minimum") \
                or _val_or_none(grade_row, f"{design_root} Min")
            d_hi = _val_or_none(grade_row, f"{design_root} Maximum") \
                or _val_or_none(grade_row, f"{design_root} Max")
            s_lo = _val_or_none(spec_row, f"{std_root} Minimum") \
                or _val_or_none(spec_row, f"{std_root} Min")
            s_hi = _val_or_none(spec_row, f"{std_root} Maximum") \
                or _val_or_none(spec_row, f"{std_root} Max")
        else:
            d_lo = _val_or_none(grade_row, f"{design_root} Minimum")
            d_hi = _val_or_none(grade_row, f"{design_root} Maximum")
            s_lo = _val_or_none(spec_row, f"{std_root} Minimum")
            s_hi = _val_or_none(spec_row, f"{std_root} Maximum")
        rows.append(_check_one_element(element, d_lo, d_hi, s_lo, s_hi))

    n_pass = sum(1 for r in rows if r.verdict == "PASS")
    n_fail = sum(1 for r in rows if r.verdict == "FAIL")
    n_na = sum(1 for r in rows if r.verdict == "N/A")
    overall = "PASS" if n_fail == 0 else "FAIL"
    return ChemReport(rows=rows, verdict=overall, n_pass=n_pass, n_fail=n_fail, n_na=n_na)


# ---------------------------------------------------------------------------
# helpers — mech (Deboer + spec compare)
# ---------------------------------------------------------------------------


def _spec_mech_row(spec: str, thickness_mm: float) -> pd.Series | None:
    df = load_hr_mech_std()
    sub = df[df["Specification"].astype(str) == spec]
    if sub.empty:
        return None

    def _t_match(r: pd.Series) -> bool:
        try:
            t_lo = float(r.get("Dimension Std Thickness Min")) if pd.notna(r.get("Dimension Std Thickness Min")) else 0.0
            t_hi = float(r.get("Dimension Std Thickness Max")) if pd.notna(r.get("Dimension Std Thickness Max")) else 1e9
        except (TypeError, ValueError):
            return True
        return t_lo <= thickness_mm <= t_hi

    sub_filtered = sub[sub.apply(_t_match, axis=1)]
    if sub_filtered.empty:
        return sub.iloc[0]
    return sub_filtered.iloc[0]


def _composition_from_grade_row(grade_row: pd.Series) -> tuple[dict[str, float], dict[str, float]]:
    cmin: dict[str, float] = {}
    cmax: dict[str, float] = {}
    for el in DEBOER_ELEMENTS:
        lo, hi = _design_pair(grade_row, el)
        cmin[el] = lo
        cmax[el] = hi
    return cmin, cmax


def _check_mech_property(
    name: str,
    pred_lo: float | None, pred_hi: float | None,
    std_lo: float | None, std_hi: float | None,
    unit: str,
) -> MechCheck:
    if std_lo is None and std_hi is None:
        return MechCheck(name, pred_lo, pred_hi, None, None, unit,
                         verdict="N/A", reason="standar tidak menetapkan batas")
    fail_lower = std_lo is not None and pred_lo is not None and pred_lo < std_lo
    fail_upper = std_hi is not None and pred_hi is not None and pred_hi > std_hi
    if fail_lower or fail_upper:
        why = []
        if fail_lower:
            why.append(f"predicted min {pred_lo:.1f} < std min {std_lo:.1f}")
        if fail_upper:
            why.append(f"predicted max {pred_hi:.1f} > std max {std_hi:.1f}")
        return MechCheck(name, pred_lo, pred_hi, std_lo, std_hi, unit,
                         verdict="FAIL", reason="; ".join(why))
    return MechCheck(name, pred_lo, pred_hi, std_lo, std_hi, unit, verdict="PASS")


def _build_elo_informational(spec: str, thickness_mm: float) -> MechCheck | None:
    df = load_hr_elongation_std()
    sub = df[df["Specification"].astype(str) == spec]
    if sub.empty:
        return None
    elo_min: float | None = None
    for _, r in sub.iterrows():
        try:
            t_lo = float(r.get("Thickness Minimum")) if pd.notna(r.get("Thickness Minimum")) else 0.0
            t_hi = float(r.get("Thickness Maximum")) if pd.notna(r.get("Thickness Maximum")) else 1e9
        except (TypeError, ValueError):
            continue
        if t_lo <= thickness_mm <= t_hi:
            v = r.get("Mech Std Elongation Min")
            if pd.notna(v):
                elo_min = float(v)
                break
    if elo_min is None:
        return None
    return MechCheck(
        property="ELO",
        predicted_min=None, predicted_max=None,
        std_min=elo_min, std_max=None,
        unit="%", verdict="N/A",
        reason="ELO tidak diprediksi Deboer; cek terhadap data produksi nyata",
    )


def _build_mech_report(
    grade_row: pd.Series,
    spec: str,
    thickness_mm: float,
    ft: TempCode, ct: TempCode,
) -> MechReport:
    cmin, cmax = _composition_from_grade_row(grade_row)
    deboer = deboer_calculate(
        cmin, cmax,
        {"Thickness": thickness_mm, "FT": ft.low, "CT": ct.low},
        {"Thickness": thickness_mm, "FT": ft.high, "CT": ct.high},
    )

    spec_row = _spec_mech_row(spec, thickness_mm)

    def _spec_val(col: str, sentinel: float = 999.0) -> float | None:
        if spec_row is None:
            return None
        v = spec_row.get(col)
        if pd.isna(v):
            return None
        v = float(v)
        if v >= sentinel:
            return None
        return v

    rows: list[MechCheck] = []
    pred = deboer["YS (MPa)"]
    rows.append(_check_mech_property(
        "YS", pred["min"], pred["max"],
        _spec_val("Mechanical Std YS Min"), _spec_val("Mechanical Std YS Max"),
        unit="MPa",
    ))
    pred = deboer["TS (MPa)"]
    rows.append(_check_mech_property(
        "TS", pred["min"], pred["max"],
        _spec_val("Mechanical Std Tensile Min"), _spec_val("Mechanical Std Tensile Max"),
        unit="MPa",
    ))

    elo = _build_elo_informational(spec, thickness_mm)
    if elo is not None:
        rows.append(elo)

    n_fail = sum(1 for r in rows if r.verdict == "FAIL")
    overall = "PASS" if n_fail == 0 else "FAIL"

    return MechReport(
        rows=rows, verdict=overall,
        thickness_mm=thickness_mm, ft=ft, ct=ct,
        ce_min=deboer["CE (Carbon Equivalent)"]["min"],
        ce_max=deboer["CE (Carbon Equivalent)"]["max"],
        pcm_min=deboer["PCM"]["min"],
        pcm_max=deboer["PCM"]["max"],
    )


# ---------------------------------------------------------------------------
# helpers — production history
# ---------------------------------------------------------------------------


def _history_stats(grade: str, spec: str) -> tuple[int, int, int, list[tuple[str, int]], list[tuple[str, int]]]:
    df = load_produksi_hrc()
    by_grade = df[df["Grade"].astype(str) == grade]
    by_spec = df[df["Spec Code"].astype(str) == spec]
    pair = df[(df["Grade"].astype(str) == grade) & (df["Spec Code"].astype(str) == spec)]

    top_grades_for_spec: list[tuple[str, int]] = []
    if not by_spec.empty:
        vc = by_spec["Grade"].astype(str).value_counts().head(5)
        top_grades_for_spec = [(str(g), int(c)) for g, c in vc.items()]

    top_specs_for_grade: list[tuple[str, int]] = []
    if not by_grade.empty:
        vc = by_grade["Spec Code"].astype(str).value_counts().head(5)
        top_specs_for_grade = [(str(s), int(c)) for s, c in vc.items()]

    return len(by_grade), len(by_spec), len(pair), top_grades_for_spec, top_specs_for_grade


# ---------------------------------------------------------------------------
# helpers — sweep search
# ---------------------------------------------------------------------------


def _score_mech_report(rep: MechReport) -> float:
    """Lower is better. PASS combos always win."""
    score = 0.0
    for r in rep.rows:
        if r.verdict == "FAIL":
            score += 1000.0
            if r.std_min is not None and r.predicted_min is not None and r.predicted_min < r.std_min:
                score += (r.std_min - r.predicted_min)
            if r.std_max is not None and r.predicted_max is not None and r.predicted_max > r.std_max:
                score += (r.predicted_max - r.std_max)
        elif r.verdict == "PASS":
            if r.std_min is not None and r.std_max is not None:
                centre = (r.std_min + r.std_max) / 2
                pred_centre = ((r.predicted_min or centre) + (r.predicted_max or centre)) / 2
                width = max(1.0, r.std_max - r.std_min)
                score += abs(pred_centre - centre) / width
            elif r.std_min is not None and r.predicted_min is not None:
                margin = r.predicted_min - r.std_min
                score += -min(margin, 50.0) / 50.0
    return score


def _sweep_params(
    grade_row: pd.Series,
    spec: str,
    thickness_options_mm: list[float],
    ft_codes: list[TempCode] | None = None,
    ct_codes: list[TempCode] | None = None,
    keep_best: int = 5,
) -> list[ParamCombo]:
    fts = ft_codes or list_ft_codes()
    cts = ct_codes or list_ct_codes()
    combos: list[ParamCombo] = []
    for t in thickness_options_mm:
        for ft in fts:
            for ct in cts:
                rep = _build_mech_report(grade_row, spec, t, ft, ct)
                combos.append(ParamCombo(
                    thickness_mm=t, ft=ft, ct=ct,
                    score=_score_mech_report(rep), mech=rep,
                ))
    combos.sort(key=lambda c: c.score)
    return combos[:keep_best]


# ---------------------------------------------------------------------------
# block formatters
# ---------------------------------------------------------------------------


def _fmt_pair(lo: float | None, hi: float | None, decimals: int = 4,
              hi_sentinel: float = 5.0) -> str:
    """Format a (lo, hi) pair, stripping sentinel-valued bounds.

    Values >= ``hi_sentinel`` on the upper bound are treated as "no upper
    limit" so the row reads cleanly (e.g. ``"≥ 0"`` instead of ``"0 – 9.999"``).
    """
    lo_v = lo
    hi_v = hi if (hi is None or hi < hi_sentinel) else None
    if lo_v == 0.0 and hi_v is None:
        return "-"
    return fmt.fmt_range(lo_v, hi_v, decimals=decimals)


def _format_chem_block(rep: ChemReport) -> str:
    head = (
        f"1. CHEMICAL COMPATIBILITY  ({rep.verdict};  "
        f"{rep.n_pass} PASS, {rep.n_fail} FAIL, {rep.n_na} N/A)"
    )
    rows = []
    for r in rep.rows:
        verdict = r.verdict
        if r.verdict == "FAIL":
            verdict += f"  ({r.reason})"
        rows.append([
            r.element,
            _fmt_pair(r.design_min, r.design_max),
            _fmt_pair(r.std_min, r.std_max),
            verdict,
        ])
    table = fmt.fixed_table(["Element", "Design", "Spec Std", "Verdict"], rows)
    return f"{head}\n{table}"


def _format_mech_block(rep: MechReport, swept: bool, alts: list[ParamCombo] | None = None) -> str:
    head = f"2. MECHANICAL FEASIBILITY  ({rep.verdict})"
    params = (
        f"  Production: thickness {rep.thickness_mm} mm,  "
        f"FT code {rep.ft.code} ({rep.ft.target}±{rep.ft.var}°C),  "
        f"CT code {rep.ct.code} ({rep.ct.target}±{rep.ct.var}°C)"
    )
    if swept:
        params += "  [auto-selected from sweep]"

    rows = []
    for r in rep.rows:
        # Mech values live in MPa / % scale (>>5), so use a high sentinel
        # so genuine numbers aren't stripped.
        if r.predicted_min is None and r.predicted_max is None:
            pred = "(not predicted)"
        else:
            pred = _fmt_pair(r.predicted_min, r.predicted_max,
                             decimals=1, hi_sentinel=999.0)
        std = _fmt_pair(r.std_min, r.std_max, decimals=1, hi_sentinel=999.0)
        verdict = r.verdict
        if r.verdict == "FAIL":
            verdict += f"  ({r.reason})"
        elif r.verdict == "N/A" and r.reason:
            verdict += f"  ({r.reason})"
        rows.append([r.property, pred, std, r.unit, verdict])
    table = fmt.fixed_table(["Property", "Predicted", "Std", "Unit", "Verdict"], rows)

    parts = [head, params, table]
    if alts:
        alt_lines = ["  Other combos worth considering:"]
        for c in alts:
            alt_lines.append(
                f"    - thickness {c.thickness_mm} mm, FT {c.ft.code}, CT {c.ct.code}  "
                f"→ {c.mech.verdict}   (score {c.score:.1f})"
            )
        parts.append("\n".join(alt_lines))
    return "\n".join(parts)


def _format_hardenability_block(rep: MechReport | None) -> str:
    if rep is None:
        return ""

    def _ce_verdict(ce: float | None) -> str:
        if ce is None:
            return "n/a"
        if ce < 0.40:
            return "GOOD weldability — no preheat required"
        if ce < 0.45:
            return "OK weldability — preheat 80–150 °C recommended"
        return "POOR weldability — preheat + post-heat required"

    def _pcm_verdict(p: float | None) -> str:
        if p is None:
            return "n/a"
        if p < 0.20:
            return "LOW cold-cracking risk"
        if p < 0.30:
            return "MODERATE cold-cracking risk"
        return "HIGH cold-cracking risk"

    ce_eval = rep.ce_max if rep.ce_max is not None else rep.ce_min
    pcm_eval = rep.pcm_max if rep.pcm_max is not None else rep.pcm_min
    return (
        "3. HARDENABILITY / WELDABILITY\n"
        f"  CEQ : {_fmt_pair(rep.ce_min, rep.ce_max, decimals=3)}   → {_ce_verdict(ce_eval)}\n"
        f"  PCM : {_fmt_pair(rep.pcm_min, rep.pcm_max, decimals=3)}   → {_pcm_verdict(pcm_eval)}"
    )


def _format_history_block(
    grade: str, spec: str,
    n_grade: int, n_spec: int, n_pair: int,
    top_grades_for_spec: list[tuple[str, int]],
    top_specs_for_grade: list[tuple[str, int]],
) -> str:
    lines = [
        "4. PRODUCTION HISTORY (Produksi 2021)",
        f"  Grade {grade}: {n_grade:,} coils total in 2021",
        f"  Spec  {spec}: {n_spec:,} coils total in 2021",
        f"  Pair  (grade x spec): {n_pair:,} coils  "
        + ("(NEVER produced this combination)" if n_pair == 0 else ""),
    ]
    if top_grades_for_spec:
        lines.append(f"  Top grades historically used for spec {spec}:")
        for g, c in top_grades_for_spec:
            lines.append(f"    - {g}: {c:,} coils")
    if top_specs_for_grade:
        lines.append(f"  Top specs historically using grade {grade}:")
        for s, c in top_specs_for_grade:
            lines.append(f"    - {s}: {c:,} coils")
    return "\n".join(lines)


def _overall_verdict(chem: ChemReport, mech: MechReport | None) -> str:
    chem_ok = chem.verdict in ("PASS", "N/A")
    mech_ok = (mech is None) or (mech.verdict in ("PASS", "N/A"))
    return "FEASIBLE" if (chem_ok and mech_ok) else "NOT FEASIBLE"


# ---------------------------------------------------------------------------
# tool: feasibility_analysis
# ---------------------------------------------------------------------------


def feasibility_analysis(
    steel_grade: str,
    specification: str,
    thickness_mm: float | None = None,
    ft_code: str | None = None,
    ct_code: str | None = None,
) -> str:
    """Decide whether ``steel_grade`` can satisfy ``specification``.

    Args:
        steel_grade: Steel Grade code (e.g. ``"A2010"`` or ``"0A2010"``).
        specification: Specification short or full name (e.g. ``"SS400"`` or
            ``"JIS G 3101 SS400"``).
        thickness_mm: optional plate thickness in mm. If omitted, the
            agent sweeps a default thickness set and picks the best.
        ft_code, ct_code: optional FT/CT codes (e.g. ``"G"``, ``"C"``).
    """
    grade, msg = _resolve_grade_or_message(steel_grade)
    if grade is None:
        return msg
    spec, msg = _resolve_spec_or_message(specification)
    if spec is None:
        return msg

    grade_row = get_chemical_design_row(grade)
    if grade_row is None:
        return f"Steel Grade '{grade}' resolved tapi rownya tidak terbaca."

    spec_chem = _spec_chem_row(spec)
    if spec_chem is None:
        chem_rep = ChemReport(rows=[], verdict="N/A", n_pass=0, n_fail=0, n_na=0)
        chem_block = (
            "1. CHEMICAL COMPATIBILITY\n"
            "  Spec ini tidak punya entry di HR_Chem_Std — chem check di-skip."
        )
    else:
        chem_rep = check_chemical_compatibility(grade_row, spec_chem)
        chem_block = _format_chem_block(chem_rep)

    # mech — either user-specified or swept
    mech_rep: MechReport | None = None
    if ft_code and ct_code and thickness_mm:
        ft = FT_CODES.get(ft_code.strip().upper())
        ct = CT_CODES.get(ct_code.strip().upper())
        if not ft or not ct:
            return f"FT/CT code '{ft_code}/{ct_code}' tidak valid."
        mech_rep = _build_mech_report(grade_row, spec, thickness_mm, ft, ct)
        mech_block = _format_mech_block(mech_rep, swept=False)
    else:
        sweep_thickness = [thickness_mm] if thickness_mm else _DEFAULT_THICKNESS_SWEEP_MM
        ft_subset = [FT_CODES[ft_code.strip().upper()]] if ft_code else None
        ct_subset = [CT_CODES[ct_code.strip().upper()]] if ct_code else None
        combos = _sweep_params(
            grade_row, spec, sweep_thickness,
            ft_codes=ft_subset, ct_codes=ct_subset, keep_best=3,
        )
        if combos:
            mech_rep = combos[0].mech
            mech_block = _format_mech_block(mech_rep, swept=True, alts=combos[1:])
        else:
            mech_block = "2. MECHANICAL FEASIBILITY\n  (tidak bisa dievaluasi)"

    hw_block = _format_hardenability_block(mech_rep)

    n_grade, n_spec, n_pair, top_grades_for_spec, top_specs_for_grade = _history_stats(grade, spec)
    history_block = _format_history_block(
        grade, spec, n_grade, n_spec, n_pair,
        top_grades_for_spec, top_specs_for_grade,
    )

    verdict = _overall_verdict(chem_rep, mech_rep)
    summary = (
        f"FEASIBILITY ANALYSIS — Grade {grade}  ->  Spec {spec}\n"
        f"VERDICT: {verdict}"
    )
    return fmt.join_blocks(summary, chem_block, mech_block, hw_block, history_block)


# ---------------------------------------------------------------------------
# tool: find_compatible_grades
# ---------------------------------------------------------------------------


def find_compatible_grades(specification: str, top_n: int = 10) -> str:
    """List Steel Grades whose chemical design fits the given Specification."""
    spec, msg = _resolve_spec_or_message(specification)
    if spec is None:
        return msg
    spec_chem = _spec_chem_row(spec)
    if spec_chem is None:
        return f"Spec '{spec}' tidak ada di HR_Chem_Std."

    df_grades = load_chemical_design()
    pass_grades: list[tuple[str, int]] = []
    for _, gr in df_grades.iterrows():
        rep = check_chemical_compatibility(gr, spec_chem)
        if rep.verdict == "PASS":
            pass_grades.append((str(gr["Steel Grade"]), rep.n_pass))

    if not pass_grades:
        return (
            f"COMPATIBLE GRADES FOR {spec}\n"
            f"  Tidak ada grade yang lulus full chemical compatibility."
        )

    df_prod = load_produksi_hrc()
    spec_prod = df_prod[df_prod["Spec Code"].astype(str) == spec]
    used_counts: dict[str, int] = {}
    if not spec_prod.empty:
        vc = spec_prod["Grade"].astype(str).value_counts()
        used_counts = {str(g): int(c) for g, c in vc.items()}

    # Re-rank: historical pairings first (by count desc), then unproduced grades
    # by element-match count.
    pass_set = {g for g, _ in pass_grades}
    history_rows = sorted(
        [(g, c) for g, c in used_counts.items() if g in pass_set],
        key=lambda x: -x[1],
    )
    unused_rows = sorted(
        [g for g, _ in pass_grades if g not in used_counts],
        key=lambda g: g,
    )

    rows: list[list[object]] = []
    for grade_id, count in history_rows[:top_n]:
        rows.append([grade_id, "PASS", f"{count:,} coils"])
    n_left = max(0, top_n - len(rows))
    for grade_id in unused_rows[:n_left]:
        rows.append([grade_id, "PASS", "never produced"])

    table = fmt.fixed_table(
        ["Steel Grade", "Chem", "History (2021)"],
        rows,
    )
    summary_lines = [
        f"COMPATIBLE GRADES FOR {spec}",
        f"  Total grades passing chem compatibility: {len(pass_grades)}",
    ]
    if history_rows:
        summary_lines.append(
            f"  Of those, {len(history_rows)} have actual 2021 production for this spec."
        )
    summary_lines.append(
        f"  (showing top {len(rows)}: produced grades first, then unproduced candidates)"
    )
    return "\n".join(summary_lines) + "\n\n" + table


# ---------------------------------------------------------------------------
# tool: compare_grades
# ---------------------------------------------------------------------------


def _clamp_or_none(v: float | None) -> float | None:
    if v is None:
        return None
    if v >= _STD_SENTINEL:
        return None
    return v


def compare_grades(grade_a: str, grade_b: str) -> str:
    """Side-by-side comparison of two Steel Grades."""
    a, msg = _resolve_grade_or_message(grade_a)
    if a is None:
        return msg
    b, msg = _resolve_grade_or_message(grade_b)
    if b is None:
        return msg
    if a == b:
        return f"Grade {a} dan {b} adalah grade yang sama."

    row_a = get_chemical_design_row(a)
    row_b = get_chemical_design_row(b)
    if row_a is None or row_b is None:
        return "Salah satu grade tidak ditemukan di Chemical_Design."

    rows = []
    elements = list(dict.fromkeys(DEBOER_ELEMENTS + ["Ca"]))
    for el in elements:
        col_min = f"Chemical Design {el} Minimum"
        col_max = f"Chemical Design {el} Maximum"
        a_lo = _clamp_or_none(_val_or_none(row_a, col_min))
        a_hi = _clamp_or_none(_val_or_none(row_a, col_max))
        b_lo = _clamp_or_none(_val_or_none(row_b, col_min))
        b_hi = _clamp_or_none(_val_or_none(row_b, col_max))
        if all(v in (None, 0.0, 0) for v in (a_lo, a_hi, b_lo, b_hi)):
            continue
        rows.append([el, _fmt_pair(a_lo, a_hi), _fmt_pair(b_lo, b_hi)])

    for label, lo_col, hi_col in [
        ("CEQ", "Chemical Design CEQ Minimum", "Chemical Design CEQ Maximum"),
        ("PCM", "Dsn MatCrack Parameter PCM Min", "Dsn MatCrack Parameter PCM Max"),
    ]:
        a_lo = _clamp_or_none(_val_or_none(row_a, lo_col))
        a_hi = _clamp_or_none(_val_or_none(row_a, hi_col))
        b_lo = _clamp_or_none(_val_or_none(row_b, lo_col))
        b_hi = _clamp_or_none(_val_or_none(row_b, hi_col))
        if (a_lo, a_hi, b_lo, b_hi) == (None, None, None, None):
            continue
        rows.append([label, _fmt_pair(a_lo, a_hi), _fmt_pair(b_lo, b_hi)])

    table = fmt.fixed_table(["Element", a, b], rows)

    df_prod = load_produksi_hrc()
    n_a = int((df_prod["Grade"].astype(str) == a).sum())
    n_b = int((df_prod["Grade"].astype(str) == b).sum())

    history = (
        "Production history (2021):\n"
        f"  - Grade {a}: {n_a:,} coils\n"
        f"  - Grade {b}: {n_b:,} coils"
    )

    return fmt.join_blocks(
        f"COMPARE GRADES — {a} vs {b}",
        table,
        history,
    )


# ---------------------------------------------------------------------------
# tool: recommend_production_params
# ---------------------------------------------------------------------------


def recommend_production_params(
    steel_grade: str,
    target_specification: str,
    thickness_mm: float | None = None,
    top_n: int = 5,
) -> str:
    """Sweep all FT × CT × thickness combos to find the best ones for
    hitting ``target_specification``'s mech requirements with ``steel_grade``.
    """
    grade, msg = _resolve_grade_or_message(steel_grade)
    if grade is None:
        return msg
    spec, msg = _resolve_spec_or_message(target_specification)
    if spec is None:
        return msg

    grade_row = get_chemical_design_row(grade)
    if grade_row is None:
        return f"Grade '{grade}' tidak terbaca dari Chemical_Design."

    sweep_thickness = [thickness_mm] if thickness_mm else _DEFAULT_THICKNESS_SWEEP_MM
    combos = _sweep_params(grade_row, spec, sweep_thickness, keep_best=top_n)
    if not combos:
        return "Tidak ada kombinasi yang bisa dievaluasi."

    rows = []
    for c in combos:
        ys_row = next((r for r in c.mech.rows if r.property == "YS"), None)
        ts_row = next((r for r in c.mech.rows if r.property == "TS"), None)
        ys_pred = (
            f"{ys_row.predicted_min:.0f}-{ys_row.predicted_max:.0f}" if ys_row else "-"
        )
        ts_pred = (
            f"{ts_row.predicted_min:.0f}-{ts_row.predicted_max:.0f}" if ts_row else "-"
        )
        rows.append([
            f"{c.thickness_mm} mm",
            f"FT {c.ft.code} ({c.ft.target}°C)",
            f"CT {c.ct.code} ({c.ct.target}°C)",
            ys_pred,
            ts_pred,
            c.mech.verdict,
            f"{c.score:.2f}",
        ])

    table = fmt.fixed_table(
        ["Thickness", "FT", "CT", "YS pred (MPa)", "TS pred (MPa)", "Verdict", "Score"],
        rows,
    )
    return (
        f"OPTIMAL PRODUCTION PARAMS — Grade {grade}  ->  Spec {spec}\n"
        f"  (lower score = better; sweep over standard FT/CT codes)\n\n"
        f"{table}"
    )
