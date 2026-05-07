"""End-to-end smoke tests that exercise every tool against the parquet data."""
from __future__ import annotations

import os

import pytest

from ppd_agent.tools import compliance, deboer, hrc, product_design

# Skip everything in this module when the parquet data isn't materialised
# (e.g. on a fresh CI checkout where prepare_data hasn't been run).
parquet_dir_path = os.path.join(os.path.dirname(__file__), "..", "data", "parquet")
if not os.path.isfile(os.path.join(parquet_dir_path, "produksi_2021_hrc.parquet")):
    pytest.skip("parquet data not prepared; run scripts/prepare_data.py first",
                allow_module_level=True)


# ---- Module 1: Product Design Lookup ----


def test_lookup_steel_grade() -> None:
    out = product_design.lookup_steel_grade("KI-A36", thickness_mm=8.0)
    assert "KI-A36" in out
    assert "Steel Grade" in out


def test_lookup_steel_grade_no_match() -> None:
    out = product_design.lookup_steel_grade("__NO_SUCH_SPEC__")
    assert "Tidak ditemukan" in out


def test_lookup_chem_standard() -> None:
    out = product_design.lookup_chem_standard("AS/NZS 3678 - 250")
    assert "Chem Standard" in out
    assert "**C**" in out


def test_lookup_mech_standard() -> None:
    out = product_design.lookup_mech_standard("EN 10025 S275", thickness_mm=10.0)
    assert "Mech Standard" in out
    assert "TS" in out and "YS" in out


def test_lookup_elongation_standard() -> None:
    out = product_design.lookup_elongation_standard("ABS AH32")
    assert "Elongation" in out


def test_lookup_thickness_tolerance() -> None:
    out = product_design.lookup_thickness_tolerance("HTS G 3101")
    assert "Thickness Tolerance" in out


def test_lookup_ft_ct_design() -> None:
    out = product_design.lookup_ft_ct_design("ABSA")
    assert "FT/CT Design" in out


# ---- Module 2: HRC ----


def test_hrc_filter() -> None:
    out = hrc.hrc_filter(spec_code="S275JR", sample=2)
    assert "Matched" in out


def test_hrc_statistics() -> None:
    out = hrc.hrc_statistics(["YS", "TS"], spec_code="S275JR")
    assert "YS" in out and "TS" in out


def test_hrc_histogram() -> None:
    res = hrc.hrc_histogram("YS", spec_code="S275JR")
    assert res.image_paths
    assert res.image_paths[0].exists()


def test_hrc_scatter() -> None:
    res = hrc.hrc_scatter("YS", "TS", spec_code="S275JR")
    assert res.image_paths
    assert "Pearson" in res.text


def test_hrc_correlation_heatmap() -> None:
    res = hrc.hrc_correlation_heatmap(["YS", "TS", "ELO"], spec_code="S275JR")
    assert res.image_paths


def test_hrc_lookup_coil() -> None:
    out = hrc.hrc_lookup_coil("ASC111")
    assert "ASC111" in out


# ---- Module 3: Deboer ----


def test_deboer_predict_for_grade() -> None:
    out = deboer.deboer_predict_for_grade(
        "0A1810",
        thickness_min_mm=7.5, thickness_max_mm=8.5,
        ct_min_c=580, ct_max_c=600,
        ft_min_c=850, ft_max_c=870,
    )
    assert "0A1810" in out
    assert "YS" in out and "TS" in out
    # PCM should be a sensible range, not the 50.x sentinel-poisoned value
    assert "50.238" not in out


# ---- Module 4: Compliance ----


def test_full_compliance_report() -> None:
    out = compliance.full_compliance_report("ASC111")
    assert "Chemical Compliance" in out
    assert "Mechanical Compliance" in out
    assert "PASS" in out or "FAIL" in out
