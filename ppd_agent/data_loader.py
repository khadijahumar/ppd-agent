"""Cached parquet loaders. Each table is loaded once on first access.

Production data supports multiple years: any file matching
``produksi_*_hrc.parquet`` in the parquet directory is loaded and
concatenated automatically.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import CONFIG

log = logging.getLogger(__name__)


def _path(name: str) -> Path:
    return CONFIG.parquet_dir / f"{name}.parquet"


@lru_cache(maxsize=1)
def load_ft_ct_design() -> pd.DataFrame:
    return pd.read_parquet(_path("ft_ct_design"))


@lru_cache(maxsize=1)
def load_hr_chem_std() -> pd.DataFrame:
    return pd.read_parquet(_path("hr_chem_std"))


@lru_cache(maxsize=1)
def load_hr_elongation_std() -> pd.DataFrame:
    return pd.read_parquet(_path("hr_elongation_std"))


@lru_cache(maxsize=1)
def load_hr_mech_std() -> pd.DataFrame:
    return pd.read_parquet(_path("hr_mech_std"))


@lru_cache(maxsize=1)
def load_hr_thick_toler() -> pd.DataFrame:
    return pd.read_parquet(_path("hr_thick_toler"))


@lru_cache(maxsize=1)
def load_z001() -> pd.DataFrame:
    return pd.read_parquet(_path("z001"))


@lru_cache(maxsize=1)
def load_chemical_design() -> pd.DataFrame:
    return pd.read_parquet(_path("chemical_design"))


@lru_cache(maxsize=1)
def load_produksi_hrc() -> pd.DataFrame:
    """Load ALL production HRC parquet files and concatenate them.

    Scans for ``produksi_*_hrc.parquet`` so adding a new year is as simple
    as dropping ``produksi_2022_hrc.parquet`` into the parquet directory.
    Falls back to the legacy single-file name for backward compat.
    """
    parquet_dir = CONFIG.parquet_dir
    pattern = "produksi_*_hrc.parquet"
    files = sorted(parquet_dir.glob(pattern))

    if not files:
        legacy = parquet_dir / "produksi_2021_hrc.parquet"
        if legacy.exists():
            files = [legacy]
        else:
            log.warning("No production HRC parquet files found in %s", parquet_dir)
            return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    for f in files:
        log.info("loading %s ...", f.name)
        df = pd.read_parquet(f)
        year_tag = f.stem.split("_")[1] if "_" in f.stem else "unknown"
        df["_source_year"] = year_tag
        frames.append(df)
        log.info("  loaded %d rows from %s", len(df), f.name)

    combined = pd.concat(frames, ignore_index=True)
    log.info("total production rows: %d (from %d file(s))", len(combined), len(files))
    return combined


def production_years() -> list[str]:
    """Return list of year tags available in the loaded production data."""
    df = load_produksi_hrc()
    if "_source_year" not in df.columns:
        return ["unknown"]
    return sorted(df["_source_year"].unique().tolist())


def warmup() -> None:
    """Force-load every dataset so the bot is ready before the first user message."""
    load_ft_ct_design()
    load_hr_chem_std()
    load_hr_elongation_std()
    load_hr_mech_std()
    load_hr_thick_toler()
    load_z001()
    load_chemical_design()
    load_produksi_hrc()
    years = production_years()
    log.info("production data years: %s", ", ".join(years))
