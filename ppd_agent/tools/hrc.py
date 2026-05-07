"""Module 2: HRC production data analysis (290k 2021 coils).

All tools accept the same filter signature so the agent can carry filters
across multiple analysis calls. Plotting tools return a ``ToolResult`` whose
``image_paths`` are sent to the user by the Telegram layer.
"""
from __future__ import annotations

import logging
import uuid
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # noqa: E402  -- must precede pyplot
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

from .. import format as fmt  # noqa: E402
from ..config import CONFIG  # noqa: E402
from ..data_loader import load_produksi_hrc  # noqa: E402
from ..parsing import fmt_number  # noqa: E402
from ._types import ToolResult  # noqa: E402

log = logging.getLogger(__name__)

# Numeric variables exposed for stats / plotting.
NUMERIC_VARS: list[str] = [
    "YS", "TS", "ELO", "Impact",
    "TBL_ACT", "WD_ACT", "FT_AV", "CT_AV",
    "C", "MN", "SI", "P", "S", "AL", "N", "NB", "V", "TI",
    "CU", "NI", "CR", "MO", "B", "CEQ", "PCM",
    "Prod WT", "Prod Akh", "Slab Length", "Slab Thick", "Slab Width", "Slab Weight",
]


# ---------------------------------------------------------------------------
# filter
# ---------------------------------------------------------------------------


def _apply_filters(
    df: pd.DataFrame,
    *,
    spec_code: str | None = None,
    customer: str | None = None,
    grade: str | None = None,
    coil_id: str | None = None,
    heat_no: str | None = None,
    thickness_min_mm: float | None = None,
    thickness_max_mm: float | None = None,
    width_min_mm: float | None = None,
    width_max_mm: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    only_finished: bool = True,
    extra_min: dict[str, float] | None = None,
    extra_max: dict[str, float] | None = None,
) -> pd.DataFrame:
    sub = df
    if spec_code:
        sub = sub[sub["Spec Code"].fillna("").str.contains(spec_code, case=False, na=False, regex=False)]
    if customer:
        sub = sub[sub["Customer"].fillna("").str.contains(customer, case=False, na=False, regex=False)]
    if grade:
        sub = sub[sub["Grade"].fillna("").str.contains(grade, case=False, na=False, regex=False)]
    if coil_id:
        sub = sub[sub["Coil ID"].fillna("").str.contains(coil_id, case=False, na=False, regex=False)]
    if heat_no:
        sub = sub[sub["Heat No"].fillna("").str.contains(heat_no, case=False, na=False, regex=False)]
    if thickness_min_mm is not None:
        sub = sub[sub["TBL_ACT"] >= thickness_min_mm]
    if thickness_max_mm is not None:
        sub = sub[sub["TBL_ACT"] <= thickness_max_mm]
    if width_min_mm is not None:
        sub = sub[sub["WD_ACT"] >= width_min_mm]
    if width_max_mm is not None:
        sub = sub[sub["WD_ACT"] <= width_max_mm]
    if date_from:
        sub = sub[sub["Rolldate"] >= pd.Timestamp(date_from)]
    if date_to:
        sub = sub[sub["Rolldate"] <= pd.Timestamp(date_to)]
    if only_finished:
        sub = sub[sub["Sta Akhir"] == 1.0]

    for col, lo in (extra_min or {}).items():
        if col in sub.columns:
            sub = sub[sub[col] >= lo]
    for col, hi in (extra_max or {}).items():
        if col in sub.columns:
            sub = sub[sub[col] <= hi]
    return sub


def _filter_summary(filters: dict) -> str:
    parts = []
    for k, v in filters.items():
        if v is None or v == {} or v == "" or v is False:
            continue
        parts.append(f"{k}={v}")
    return "; ".join(parts) if parts else "(no filters)"


def hrc_filter(
    spec_code: str | None = None,
    customer: str | None = None,
    grade: str | None = None,
    coil_id: str | None = None,
    heat_no: str | None = None,
    thickness_min_mm: float | None = None,
    thickness_max_mm: float | None = None,
    width_min_mm: float | None = None,
    width_max_mm: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    only_finished: bool = True,
    sample: int = 5,
) -> str:
    """Filter the HRC production dataset and return a summary."""
    df = load_produksi_hrc()
    sub = _apply_filters(
        df,
        spec_code=spec_code, customer=customer, grade=grade,
        coil_id=coil_id, heat_no=heat_no,
        thickness_min_mm=thickness_min_mm, thickness_max_mm=thickness_max_mm,
        width_min_mm=width_min_mm, width_max_mm=width_max_mm,
        date_from=date_from, date_to=date_to,
        only_finished=only_finished,
    )

    flt_str = _filter_summary({
        "spec_code": spec_code, "customer": customer, "grade": grade,
        "coil_id": coil_id, "heat_no": heat_no,
        "thickness_min_mm": thickness_min_mm, "thickness_max_mm": thickness_max_mm,
        "width_min_mm": width_min_mm, "width_max_mm": width_max_mm,
        "date_from": date_from, "date_to": date_to,
        "only_finished": only_finished,
    })

    head = (
        "HRC FILTER RESULT\n"
        f"  Filters : {flt_str}\n"
        f"  Matched : {len(sub):,} coils (out of {len(df):,} total)"
    )

    if len(sub) == 0:
        return head

    blocks: list[str] = [head]
    top_spec_rows = [[s, f"{n:,}"] for s, n in sub["Spec Code"].value_counts().head(5).items()]
    blocks.append(
        "TOP 5 SPEC CODE\n" + fmt.fixed_table(["Spec Code", "Coils"], top_spec_rows)
    )
    top_cust_rows = [[c, f"{n:,}"] for c, n in sub["Customer"].value_counts().head(5).items()]
    blocks.append(
        "TOP 5 CUSTOMER\n" + fmt.fixed_table(["Customer", "Coils"], top_cust_rows)
    )

    if sample > 0 and len(sub) > 0:
        rows = []
        for _, r in sub.head(sample).iterrows():
            date_s = "-" if pd.isna(r.get("Rolldate")) else pd.Timestamp(r["Rolldate"]).strftime("%Y-%m-%d")
            rows.append([
                r.get("Coil ID", "-"), r.get("Spec Code", "-"), r.get("Grade", "-"),
                fmt_number(r.get("TBL_ACT")), fmt_number(r.get("WD_ACT")),
                fmt_number(r.get("YS")), fmt_number(r.get("TS")),
                fmt_number(r.get("ELO")), fmt_number(r.get("FT_AV")),
                fmt_number(r.get("CT_AV")), date_s,
            ])
        blocks.append(
            f"SAMPLE  ({min(sample, len(sub))} coils)\n"
            + fmt.fixed_table(
                ["Coil ID", "Spec", "Grade", "TBL", "WD",
                 "YS", "TS", "ELO", "FT", "CT", "Date"],
                rows,
            )
        )

    return fmt.join_blocks(*blocks)


# ---------------------------------------------------------------------------
# statistics
# ---------------------------------------------------------------------------


def hrc_statistics(
    variables: list[str] | None = None,
    *,
    spec_code: str | None = None,
    customer: str | None = None,
    grade: str | None = None,
    thickness_min_mm: float | None = None,
    thickness_max_mm: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    only_finished: bool = True,
) -> str:
    """Compute mean/std/min/max/quantiles for the requested numeric variables."""
    if variables is None or len(variables) == 0:
        variables = ["YS", "TS", "ELO", "FT_AV", "CT_AV", "TBL_ACT"]
    invalid = [v for v in variables if v not in NUMERIC_VARS]
    variables = [v for v in variables if v in NUMERIC_VARS]
    df = load_produksi_hrc()
    sub = _apply_filters(
        df,
        spec_code=spec_code, customer=customer, grade=grade,
        thickness_min_mm=thickness_min_mm, thickness_max_mm=thickness_max_mm,
        date_from=date_from, date_to=date_to, only_finished=only_finished,
    )
    if len(sub) == 0:
        return "Tidak ada data setelah filter — coba longgarkan kriteria."

    head = f"HRC STATISTICS  ({len(sub):,} coils)"
    if invalid:
        head += f"\n  (variabel tidak dikenal diabaikan: {', '.join(invalid)})"
    rows: list[list[object]] = []
    for v in variables:
        s = pd.to_numeric(sub[v], errors="coerce").dropna()
        if len(s) == 0:
            rows.append([v, "0", "-", "-", "-", "-", "-", "-", "-"])
            continue
        rows.append([
            v, f"{len(s):,}",
            fmt_number(float(s.mean()), 3), fmt_number(float(s.std()), 3),
            fmt_number(float(s.min()), 3), fmt_number(float(s.quantile(0.25)), 3),
            fmt_number(float(s.median()), 3), fmt_number(float(s.quantile(0.75)), 3),
            fmt_number(float(s.max()), 3),
        ])
    table = fmt.fixed_table(
        ["Variable", "n", "Mean", "Std", "Min", "P25", "Median", "P75", "Max"],
        rows,
    )
    return f"{head}\n{table}"


# ---------------------------------------------------------------------------
# plots
# ---------------------------------------------------------------------------


def _plot_path(prefix: str) -> Path:
    return CONFIG.plots_dir / f"{prefix}_{uuid.uuid4().hex[:8]}.png"


def _filtered_for_plot(**filters) -> pd.DataFrame:
    df = load_produksi_hrc()
    return _apply_filters(df, **filters)


def hrc_histogram(
    variable: str,
    *,
    spec_code: str | None = None,
    customer: str | None = None,
    grade: str | None = None,
    thickness_min_mm: float | None = None,
    thickness_max_mm: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    only_finished: bool = True,
    bins: int = 40,
) -> ToolResult:
    """Histogram of a numeric variable across the filtered subset."""
    if variable not in NUMERIC_VARS:
        return ToolResult(text=f"Variable '{variable}' tidak dikenal. Pilihan: {NUMERIC_VARS}")
    sub = _filtered_for_plot(
        spec_code=spec_code, customer=customer, grade=grade,
        thickness_min_mm=thickness_min_mm, thickness_max_mm=thickness_max_mm,
        date_from=date_from, date_to=date_to, only_finished=only_finished,
    )
    s = pd.to_numeric(sub[variable], errors="coerce").dropna()
    if len(s) == 0:
        return ToolResult(text="Tidak ada data setelah filter — histogram tidak dibuat.")

    path = _plot_path(f"hist_{variable}")
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.hist(s, bins=bins, color="#4F81BD", edgecolor="#1F4E78", alpha=0.85)
    ax.set_title(f"Distribution of {variable} (n={len(s):,})")
    ax.set_xlabel(variable); ax.set_ylabel("Frequency")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

    text = (
        f"HISTOGRAM — {variable}\n"
        f"  n    : {len(s):,}\n"
        f"  mean : {fmt_number(float(s.mean()))}\n"
        f"  std  : {fmt_number(float(s.std()))}\n"
        f"  min  : {fmt_number(float(s.min()))}\n"
        f"  max  : {fmt_number(float(s.max()))}"
    )
    return ToolResult(text=text, image_paths=[path])


def hrc_scatter(
    x: str,
    y: str,
    *,
    spec_code: str | None = None,
    customer: str | None = None,
    grade: str | None = None,
    thickness_min_mm: float | None = None,
    thickness_max_mm: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    only_finished: bool = True,
    max_points: int = 5000,
) -> ToolResult:
    if x not in NUMERIC_VARS or y not in NUMERIC_VARS:
        return ToolResult(text=f"Variabel x/y harus salah satu dari: {NUMERIC_VARS}")
    sub = _filtered_for_plot(
        spec_code=spec_code, customer=customer, grade=grade,
        thickness_min_mm=thickness_min_mm, thickness_max_mm=thickness_max_mm,
        date_from=date_from, date_to=date_to, only_finished=only_finished,
    )
    pair = sub[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pair) == 0:
        return ToolResult(text="Tidak ada data setelah filter — scatter tidak dibuat.")
    if len(pair) > max_points:
        pair = pair.sample(max_points, random_state=42)
    corr = float(pair[x].corr(pair[y]))

    path = _plot_path(f"scatter_{x}_{y}")
    fig, ax = plt.subplots(figsize=(8, 5.5))
    ax.scatter(pair[x], pair[y], s=8, alpha=0.45, color="#3a7bd5")
    ax.set_title(f"{y} vs {x}  (n={len(pair):,}, r={corr:.3f})")
    ax.set_xlabel(x); ax.set_ylabel(y)
    ax.grid(True, alpha=0.3)
    # regression line
    if len(pair) >= 2:
        m, b = np.polyfit(pair[x], pair[y], 1)
        xs = np.linspace(pair[x].min(), pair[x].max(), 100)
        ax.plot(xs, m * xs + b, color="#d9534f", linestyle="--", linewidth=1.5,
                label=f"y = {m:.4f}·x + {b:.3f}")
        ax.legend(loc="best", fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

    return ToolResult(
        text=(
            f"SCATTER — {y} vs {x}\n"
            f"  n          : {len(pair):,}\n"
            f"  Pearson r  : {corr:.3f}"
        ),
        image_paths=[path],
    )


def hrc_correlation_heatmap(
    variables: list[str] | None = None,
    *,
    spec_code: str | None = None,
    customer: str | None = None,
    grade: str | None = None,
    thickness_min_mm: float | None = None,
    thickness_max_mm: float | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    only_finished: bool = True,
) -> ToolResult:
    if not variables or len(variables) < 2:
        variables = ["YS", "TS", "ELO", "TBL_ACT", "FT_AV", "CT_AV", "C", "MN", "CEQ"]
    variables = [v for v in variables if v in NUMERIC_VARS]
    if len(variables) < 2:
        return ToolResult(text=f"Butuh >=2 variabel valid. Pilihan: {NUMERIC_VARS}")

    sub = _filtered_for_plot(
        spec_code=spec_code, customer=customer, grade=grade,
        thickness_min_mm=thickness_min_mm, thickness_max_mm=thickness_max_mm,
        date_from=date_from, date_to=date_to, only_finished=only_finished,
    )
    data = sub[variables].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < 2:
        return ToolResult(text="Tidak ada data cukup untuk heatmap.")
    corr = data.corr()

    path = _plot_path("corr")
    fig, ax = plt.subplots(figsize=(0.7 * len(variables) + 3, 0.6 * len(variables) + 2.5))
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0,
                vmin=-1, vmax=1, square=True, ax=ax, cbar_kws={"shrink": 0.8})
    ax.set_title(f"Correlation Heatmap (n={len(data):,})")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)

    return ToolResult(
        text=(
            f"CORRELATION HEATMAP\n"
            f"  variables : {len(variables)}\n"
            f"  samples   : {len(data):,}"
        ),
        image_paths=[path],
    )


# ---------------------------------------------------------------------------
# coil lookup
# ---------------------------------------------------------------------------


def hrc_lookup_coil(coil_id: str) -> str:
    """Return full details for a single coil."""
    df = load_produksi_hrc()
    sub = df[df["Coil ID"].fillna("").str.upper() == coil_id.strip().upper()]
    if sub.empty:
        # fallback: substring match
        sub = df[df["Coil ID"].fillna("").str.contains(coil_id, case=False, na=False, regex=False)]
    if sub.empty:
        return f"Coil ID '{coil_id}' tidak ditemukan."
    if len(sub) > 5:
        return (f"Ditemukan {len(sub)} coil yang cocok dengan '{coil_id}' — terlalu banyak. "
                f"Berikan Coil ID yang lebih spesifik. Contoh: {', '.join(sub['Coil ID'].head(5).astype(str))}.")

    blocks: list[str] = [f"COIL DETAILS — {len(sub)} match"]
    for _, r in sub.iterrows():
        date_s = "-" if pd.isna(r.get("Rolldate")) else pd.Timestamp(r["Rolldate"]).strftime("%Y-%m-%d")
        identity = [
            fmt.kv("Coil ID", r.get("Coil ID")),
            fmt.kv("Heat / Slab", f"{r.get('Heat No')} / {r.get('Slab No')}"),
            fmt.kv("Spec Code", r.get("Spec Code")),
            fmt.kv("Grade", r.get("Grade")),
            fmt.kv("Customer", r.get("Customer")),
            fmt.kv("Thickness", f"{fmt_number(r.get('TBL_ACT'))} mm"),
            fmt.kv("Width", f"{fmt_number(r.get('WD_ACT'))} mm"),
            fmt.kv("YS / TS", f"{fmt_number(r.get('YS'))} / {fmt_number(r.get('TS'))} N/mm²"),
            fmt.kv("ELO / Impact", f"{fmt_number(r.get('ELO'))} / {fmt_number(r.get('Impact'))}"),
            fmt.kv("FT / CT", f"{fmt_number(r.get('FT_AV'))} / {fmt_number(r.get('CT_AV'))} °C"),
            fmt.kv("CEQ / PCM", f"{fmt_number(r.get('CEQ'))} / {fmt_number(r.get('PCM'))}"),
            fmt.kv("Rolldate", f"{date_s}    Status: {r.get('Sta Akhir')}"),
        ]
        comp_pairs = []
        for el in ["C", "MN", "SI", "P", "S", "AL", "N", "NB", "V", "TI", "CU", "NI", "CR", "MO", "B"]:
            v = r.get(el)
            if pd.notna(v):
                comp_pairs.append((el, fmt_number(float(v))))
        comp_block = ""
        if comp_pairs:
            comp_block = "  COMPOSITION (%)\n" + "\n".join(
                f"    {el:<3} : {val}" for el, val in comp_pairs
            )
        reasons = [r.get(c) for c in ["Reason 1", "Reason 2", "Reason 3"] if pd.notna(r.get(c))]
        reason_block = (
            "  REASONS\n    " + ", ".join(map(str, reasons))
            if reasons else ""
        )
        blocks.append("\n".join(identity))
        if comp_block:
            blocks.append(comp_block)
        if reason_block:
            blocks.append(reason_block)
    return fmt.join_blocks(*blocks)
