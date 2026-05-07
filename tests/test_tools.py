"""End-to-end smoke tests that exercise every tool against the parquet data."""
from __future__ import annotations

import os

import pytest

from ppd_agent.tools import compliance, deboer, feasibility, hrc, product_design

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
    assert "CHEM STANDARD" in out
    assert "C " in out  # element row


def test_lookup_mech_standard() -> None:
    out = product_design.lookup_mech_standard("EN 10025 S275", thickness_mm=10.0)
    assert "MECH STANDARD" in out
    assert "TS" in out and "YS" in out


def test_lookup_elongation_standard() -> None:
    out = product_design.lookup_elongation_standard("ABS AH32")
    assert "ELONGATION" in out


def test_lookup_thickness_tolerance() -> None:
    out = product_design.lookup_thickness_tolerance("HTS G 3101")
    assert "THICKNESS TOLERANCE" in out


def test_lookup_ft_ct_design() -> None:
    out = product_design.lookup_ft_ct_design("ABSA")
    assert "FT/CT DESIGN" in out


def test_no_markdown_in_outputs() -> None:
    """Verify outputs don't contain pipe-tables, ### headers, or **bold**."""
    samples = [
        product_design.lookup_steel_grade("KI-A36", thickness_mm=8.0),
        product_design.lookup_chem_standard("AS/NZS 3678 - 250"),
        product_design.lookup_mech_standard("EN 10025 S275", thickness_mm=10.0),
        product_design.lookup_ft_ct_design("ABSA"),
    ]
    for s in samples:
        assert "###" not in s, f"markdown header in: {s[:80]!r}"
        assert "**" not in s, f"bold in: {s[:80]!r}"
        assert "|" not in s.replace("±", ""), f"pipe-table in: {s[:80]!r}"


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
    assert "CHEMICAL COMPLIANCE" in out
    assert "MECHANICAL COMPLIANCE" in out
    assert "PASS" in out or "FAIL" in out
    # plain-text only
    assert "###" not in out
    assert "**" not in out
    assert "|" not in out


# ---- Module 5: Feasibility ----


def test_feasibility_analysis_full_spec() -> None:
    out = feasibility.feasibility_analysis(
        "A2010", "JIS G 3101 SS400",
        thickness_mm=8.0, ft_code="G", ct_code="C",
    )
    assert "FEASIBILITY ANALYSIS" in out
    assert "VERDICT:" in out
    assert "CHEMICAL COMPATIBILITY" in out
    assert "MECHANICAL FEASIBILITY" in out
    assert "HARDENABILITY" in out
    assert "PRODUCTION HISTORY" in out
    # plain text
    assert "###" not in out
    assert "**" not in out
    assert "|" not in out


def test_feasibility_analysis_shortname_grade() -> None:
    """User can use 'A2010' instead of '0A2010'."""
    out = feasibility.feasibility_analysis(
        "A2010", "JIS G 3101 SS400",
        thickness_mm=8.0, ft_code="G", ct_code="C",
    )
    assert "0A2010" in out  # canonical form should appear


def test_feasibility_ambiguous_spec_returns_candidates() -> None:
    """Shortname 'SS400' matches multiple specs — tool surfaces them."""
    out = feasibility.feasibility_analysis(
        "A2010", "SS400",
        thickness_mm=8.0, ft_code="G", ct_code="C",
    )
    assert "ambigu" in out.lower() or "JIS G 3101 SS400" in out


def test_feasibility_no_params_runs_sweep() -> None:
    """When ft/ct/thickness omitted, app sweeps and picks the best."""
    out = feasibility.feasibility_analysis("A2010", "JIS G 3101 SS400")
    assert "FEASIBILITY ANALYSIS" in out
    assert "VERDICT:" in out


def test_find_compatible_grades() -> None:
    out = feasibility.find_compatible_grades("JIS G 3101 SS400", top_n=5)
    assert "COMPATIBLE GRADES" in out
    assert "PASS" in out or "never produced" in out or "coils" in out


def test_compare_grades() -> None:
    out = feasibility.compare_grades("A2010", "0A1810")
    assert "COMPARE GRADES" in out
    assert "0A2010" in out and "0A1810" in out


def test_recommend_production_params() -> None:
    out = feasibility.recommend_production_params(
        "A2010", "JIS G 3101 SS400",
        thickness_mm=8.0, top_n=3,
    )
    assert "OPTIMAL PRODUCTION PARAMS" in out
    # Output should mention FT/CT codes
    assert "FT " in out and "CT " in out
