"""One-time data preparation: convert xlsx → parquet with parsed numerics.

Run once after first install (or whenever raw xlsx files change):

    python scripts/prepare_data.py
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

from ppd_agent.config import CONFIG
from ppd_agent.parsing import parse_number

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("prepare_data")


# Mapping: parquet output name -> (xlsx file basename, sheet name or None)
SOURCES: dict[str, tuple[str, str | None]] = {
    "ft_ct_design": ("FT_CT_Design.xlsx", "Sheet1"),
    "hr_chem_std": ("HR_Chem_Std.xlsx", "Sheet1"),
    "hr_elongation_std": ("HR_Elongation_Std.xlsx", "Sheet1"),
    "hr_mech_std": ("HR_Mech_Std.xlsx", "Sheet1"),
    "hr_thick_toler": ("HR_Thick_Toler.xlsx", "Sheet1"),
    "z001": ("Z001.xlsx", "Sheet1"),
    "chemical_design": ("Chemical_Design.xls", "Sheet1"),
    "produksi_2021_hrc": ("Produksi_2021_HRC.xlsx", "2021 HRC"),
}

# Columns we KEEP as raw text (do not coerce to float). Everything else is
# attempted as a number; if >=80% of non-null rows parse, the column becomes
# float, otherwise it stays as cleaned string.
TEXT_HINTS = {
    "specification", "spec code", "spec", "grade", "steel grade",
    "hr spec code", "dim thickness", "dim width", "thickness range",
    "width range", "finish temperature code", "coil temperature code",
    "standard direction of ts", "standard direction of impact",
    "flexibility", "chemical standard ceq code",
    "coil id", "coil samp", "heat no", "slab no", "customer",
    "rolldate", "reason 1", "reason 2", "reason 3", "po id", "status",
    "gauge_length",
}


def _is_text_col(name: str) -> bool:
    n = name.strip().lower()
    return n in TEXT_HINTS


def _coerce_numeric(series: pd.Series) -> tuple[pd.Series, bool]:
    """Try to parse every cell as a float. Returns (parsed_series, ok)
    where ok=True only if >=80% of non-null cells parsed successfully.
    """
    non_null = series.dropna()
    if len(non_null) == 0:
        return series, False
    parsed = series.map(lambda v: parse_number(v))
    ok_count = parsed[non_null.index].notna().sum()
    if ok_count / max(len(non_null), 1) >= 0.8:
        return parsed.astype("float64"), True
    return series, False


def convert_one(src_path: Path, sheet: str | None, dst_path: Path) -> None:
    log.info("Reading %s [%s]", src_path.name, sheet)
    df = pd.read_excel(src_path, sheet_name=sheet)

    # strip whitespace in column names
    df.columns = [str(c).strip() for c in df.columns]

    n_rows, n_cols = df.shape
    log.info("  shape: %d rows x %d cols", n_rows, n_cols)

    # coerce numeric columns
    for col in df.columns:
        if _is_text_col(col):
            df[col] = df[col].astype("string")
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            continue
        new_series, ok = _coerce_numeric(df[col])
        if ok:
            df[col] = new_series

    log.info("  -> saving %s", dst_path.name)
    df.to_parquet(dst_path, index=False, compression="snappy")


def main() -> int:
    CONFIG.ensure_dirs()
    log.info("Raw dir   : %s", CONFIG.raw_dir)
    log.info("Parquet dir: %s", CONFIG.parquet_dir)

    n_ok = 0
    n_err = 0
    for name, (filename, sheet) in SOURCES.items():
        src = CONFIG.raw_dir / filename
        dst = CONFIG.parquet_dir / f"{name}.parquet"
        if not src.exists():
            log.warning("missing %s, skipping %s", src, name)
            n_err += 1
            continue
        try:
            convert_one(src, sheet, dst)
            n_ok += 1
        except Exception as exc:
            log.exception("failed to convert %s: %s", name, exc)
            n_err += 1

    log.info("done. %d ok, %d errors", n_ok, n_err)
    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
