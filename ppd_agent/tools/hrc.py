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

    out = [
        "### HRC Filter Result",
        f"Filters: {flt_str}",
        f"Matched: **{len(sub):,} coils** (out of {len(df):,} total)",
    ]

    if len(sub) == 0:
        return "\n".join(out)

    # quick distribution highlights
    out.append("")
    out.append("**Top 5 Spec Code:**")
    for spec, n in sub["Spec Code"].value_counts().head(5).items():
        out.append(f"  - {spec}: {n:,}")
    out.append("")
    out.append("**Top 5 Customer:**")
    for cust, n in sub["Customer"].value_counts().head(5).items():
        out.append(f"  - {cust}: {n:,}")

    if sample > 0 and len(sub) > 0:
        out.append("")
        out.append(f"**Sample {min(sample, len(sub))} coil:**")
        out.append("| Coil ID | Spec | Grade | TBL | WD | YS | TS | ELO | FT | CT | Date |")
        out.append("|---|---|---|---|---|---|---|---|---|---|---|")
        for _, r in sub.head(sample).iterrows():
            date_s = "-" if pd.isna(r.get("Rolldate")) else pd.Timestamp(r["Rolldate"]).strftime("%Y-%m-%d")
            out.append(
                f"| {r.get('Coil ID', '-')} | {r.get('Spec Code', '-')} | {r.get('Grade', '-')} | "
                f"{fmt_number(r.get('TBL_ACT'))} | {fmt_number(r.get('WD_ACT'))} | "
                f"{fmt_number(r.get('YS'))} | {fmt_number(r.get('TS'))} | "
                f"{fmt_number(r.get('ELO'))} | {fmt_number(r.get('FT_AV'))} | "
                f"{fmt_number(r.get('CT_AV'))} | {date_s} |"
            )

    return "\n".join(out)


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

    out = [f"### HRC Statistics ({len(sub):,} coils)"]
    if invalid:
        out.append(f"_(variabel tidak dikenal diabaikan: {', '.join(invalid)})_")
    out.append("")
    out.append("| Variable | n | Mean | Std | Min | P25 | Median | P75 | Max |")
    out.append("|---|---|---|---|---|---|---|---|---|")
    for v in variables:
        s = pd.to_numeric(sub[v], errors="coerce").dropna()
        if len(s) == 0:
            out.append(f"| {v} | 0 | - | - | - | - | - | - | - |")
            continue
        out.append(
            f"| **{v}** | {len(s):,} | "
            f"{fmt_number(float(s.mean()), 3)} | {fmt_number(float(s.std()), 3)} | "
            f"{fmt_number(float(s.min()), 3)} | {fmt_number(float(s.quantile(0.25)), 3)} | "
            f"{fmt_number(float(s.median()), 3)} | {fmt_number(float(s.quantile(0.75)), 3)} | "
            f"{fmt_number(float(s.max()), 3)} |"
        )
    return "\n".join(out)


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
        f"Histogram **{variable}** dibuat.\n"
        f"- n = {len(s):,}, mean = {fmt_number(float(s.mean()))}, "
        f"std = {fmt_number(float(s.std()))}, min = {fmt_number(float(s.min()))}, "
        f"max = {fmt_number(float(s.max()))}"
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
        text=f"Scatter plot **{y} vs {x}** dibuat. Pearson r = {corr:.3f}, n = {len(pair):,}.",
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
        text=f"Correlation heatmap dibuat untuk {len(variables)} variabel pada {len(data):,} sample.",
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

    out = [f"### Coil Details — {len(sub)} match"]
    for _, r in sub.iterrows():
        date_s = "-" if pd.isna(r.get("Rolldate")) else pd.Timestamp(r["Rolldate"]).strftime("%Y-%m-%d")
        out.append("")
        out.append(f"**Coil {r.get('Coil ID')}**")
        out.append(f"  - Heat / Slab: {r.get('Heat No')} / {r.get('Slab No')}")
        out.append(f"  - Spec: {r.get('Spec Code')}  |  Grade: {r.get('Grade')}  |  Customer: {r.get('Customer')}")
        out.append(f"  - Dim: TBL={fmt_number(r.get('TBL_ACT'))} mm, WD={fmt_number(r.get('WD_ACT'))} mm")
        out.append(f"  - Mech: YS={fmt_number(r.get('YS'))} N/mm², TS={fmt_number(r.get('TS'))} N/mm², "
                   f"ELO={fmt_number(r.get('ELO'))}, Impact={fmt_number(r.get('Impact'))} J")
        out.append(f"  - Rolling: FT={fmt_number(r.get('FT_AV'))} °C, CT={fmt_number(r.get('CT_AV'))} °C")
        out.append("  - Komposisi (%):")
        for el in ["C", "MN", "SI", "P", "S", "AL", "N", "NB", "V", "TI", "CU", "NI", "CR", "MO", "B"]:
            v = r.get(el)
            if pd.notna(v):
                out.append(f"      {el}={fmt_number(float(v))}", )
        out.append(f"  - CEQ={fmt_number(r.get('CEQ'))}, PCM={fmt_number(r.get('PCM'))}")
        out.append(f"  - Rolldate: {date_s}  |  Status: {r.get('Sta Akhir')}")
        reasons = [r.get(c) for c in ["Reason 1", "Reason 2", "Reason 3"] if pd.notna(r.get(c))]
        if reasons:
            out.append(f"  - Reasons: {', '.join(map(str, reasons))}")
    return "\n".join(out)
