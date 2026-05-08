"""Data quality filters for production data.

Rules:
- Mechanical historical data: filter out rows where YS/TS/ELO are all empty,
  then deduplicate by ``Coil Samp`` (keep first).
- Chemical historical data: filter out rows where C is empty,
  then deduplicate by ``Heat No`` (keep first).
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)


def filter_mechanical(df: pd.DataFrame) -> pd.DataFrame:
    """Filter production data for mechanical analysis.

    1. Remove rows where YS, TS, and ELO are ALL empty/NaN.
    2. Deduplicate by ``Coil Samp`` (keep first occurrence).
    """
    if df.empty:
        return df

    mech_cols = ["YS", "TS", "ELO"]
    existing = [c for c in mech_cols if c in df.columns]
    if not existing:
        return df

    # Keep rows where at least one mech property is non-null
    mask = df[existing].notna().any(axis=1)
    filtered = df[mask].copy()

    # Deduplicate by Coil Samp
    if "Coil Samp" in filtered.columns:
        before = len(filtered)
        filtered = filtered.drop_duplicates(subset=["Coil Samp"], keep="first")
        dupes = before - len(filtered)
        if dupes > 0:
            log.debug("mechanical dedup: removed %d duplicate Coil Samp rows", dupes)

    return filtered


def filter_chemical(df: pd.DataFrame) -> pd.DataFrame:
    """Filter production data for chemical analysis.

    1. Remove rows where C (Carbon) is empty/NaN.
    2. Deduplicate by ``Heat No`` (keep first occurrence).
    """
    if df.empty:
        return df

    if "C" not in df.columns:
        return df

    # Keep rows where C is non-null
    filtered = df[df["C"].notna()].copy()

    # Deduplicate by Heat No
    if "Heat No" in filtered.columns:
        before = len(filtered)
        filtered = filtered.drop_duplicates(subset=["Heat No"], keep="first")
        dupes = before - len(filtered)
        if dupes > 0:
            log.debug("chemical dedup: removed %d duplicate Heat No rows", dupes)

    return filtered
