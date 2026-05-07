"""Resolvers that map user-friendly shortnames to canonical IDs.

`resolve_steel_grade("A2010")` → returns the actual ``Steel Grade`` value
present in ``Chemical_Design`` (typically ``"0A2010"``).

`resolve_specification("SS400")` → list of candidate full-name specifications
present in either ``HR_Chem_Std`` or ``HR_Mech_Std`` (e.g. ``"JIS G 3101 SS400"``,
``"MIN SS400"``).

Both work case-insensitively and tolerate optional leading zeros, slashes, etc.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from .data_loader import load_chemical_design, load_hr_chem_std, load_hr_mech_std


@dataclass
class GradeMatch:
    canonical: str
    matched_via: str  # "exact", "alias", "substring"


@dataclass
class SpecMatch:
    canonical: str
    matched_via: str
    has_chem_std: bool
    has_mech_std: bool


# ---------------------------------------------------------------------------
# steel grade
# ---------------------------------------------------------------------------


def _normalise_grade(raw: str) -> str:
    return re.sub(r"[\s\-_/]+", "", raw or "").upper()


def resolve_steel_grade(query: str) -> list[GradeMatch]:
    """Find canonical Steel Grade(s) for a possibly-abbreviated query.

    Returns up to 5 candidates. Empty list if nothing matches.
    """
    if not query or not query.strip():
        return []
    df = load_chemical_design()
    grades = df["Steel Grade"].astype(str).tolist()

    target = _normalise_grade(query)
    if not target:
        return []

    out: list[GradeMatch] = []
    seen: set[str] = set()

    # 1) exact (post-normalise) match
    for g in grades:
        if _normalise_grade(g) == target and g not in seen:
            out.append(GradeMatch(canonical=g, matched_via="exact"))
            seen.add(g)

    # 2) leading-zero variants
    if not out:
        zero_variants = {target, "0" + target, "00" + target, target.lstrip("0")}
        for g in grades:
            if _normalise_grade(g) in zero_variants and g not in seen:
                out.append(GradeMatch(canonical=g, matched_via="alias"))
                seen.add(g)

    # 3) substring fallback (any direction)
    if not out:
        for g in grades:
            n = _normalise_grade(g)
            if (target in n or n in target) and g not in seen:
                out.append(GradeMatch(canonical=g, matched_via="substring"))
                seen.add(g)
                if len(out) >= 5:
                    break

    return out


# ---------------------------------------------------------------------------
# specification
# ---------------------------------------------------------------------------


def _normalise_spec(raw: str) -> str:
    return re.sub(r"[\s\-_/.,:;]+", "", raw or "").upper()


def _all_specifications() -> set[str]:
    chem = load_hr_chem_std()["Specification"].dropna().astype(str)
    mech = load_hr_mech_std()["Specification"].dropna().astype(str)
    return set(chem) | set(mech)


_TOKEN_SPLIT = re.compile(r"[\s\-_/.,:;+]+")


def _spec_tokens(raw: str) -> list[str]:
    return [t.upper() for t in _TOKEN_SPLIT.split(raw or "") if t]


def resolve_specification(query: str, max_results: int = 5) -> list[SpecMatch]:
    """Find canonical Specification(s) for a possibly-abbreviated query.

    Searches both ``HR_Chem_Std`` and ``HR_Mech_Std``. Returns up to
    ``max_results`` candidates ranked:
        exact > token-exact > prefix > substring.
    """
    if not query or not query.strip():
        return []
    target = _normalise_spec(query)
    if not target:
        return []
    target_token = query.strip().upper()

    chem_specs = set(load_hr_chem_std()["Specification"].dropna().astype(str))
    mech_specs = set(load_hr_mech_std()["Specification"].dropna().astype(str))
    all_specs = sorted(chem_specs | mech_specs)

    exact: list[str] = []
    token_exact: list[str] = []
    prefix: list[str] = []
    substring: list[str] = []
    for s in all_specs:
        n = _normalise_spec(s)
        if n == target:
            exact.append(s)
            continue
        if target_token in _spec_tokens(s):
            token_exact.append(s)
            continue
        if n.endswith(target) or n.startswith(target):
            prefix.append(s)
        elif target in n:
            substring.append(s)

    ordered: list[tuple[str, str]] = (
        [(s, "exact") for s in exact]
        + [(s, "alias") for s in token_exact]
        + [(s, "prefix") for s in prefix]
        + [(s, "substring") for s in substring]
    )
    out: list[SpecMatch] = []
    for canonical, via in ordered[:max_results]:
        out.append(SpecMatch(
            canonical=canonical,
            matched_via=via,
            has_chem_std=canonical in chem_specs,
            has_mech_std=canonical in mech_specs,
        ))
    return out


def get_chemical_design_row(steel_grade_canonical: str) -> pd.Series | None:
    df = load_chemical_design()
    sub = df[df["Steel Grade"].astype(str) == steel_grade_canonical]
    if sub.empty:
        return None
    return sub.iloc[0]
