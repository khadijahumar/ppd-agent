"""Cached parquet loaders. Each table is loaded once on first access."""
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
    """Production data 2021 HRC. ~290k rows; cached so subsequent calls are instant."""
    log.info("loading produksi_2021_hrc.parquet ...")
    df = pd.read_parquet(_path("produksi_2021_hrc"))
    log.info("  loaded %d rows", len(df))
    return df


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
