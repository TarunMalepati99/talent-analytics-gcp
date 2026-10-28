"""Unit tests for the significance layer and the extract validation gate."""

import numpy as np
import pandas as pd
import pytest

from analysis.attrition_significance import (
    cramers_v, design_matrix, effect_label, load_spec, wilson_ci,
)
from scripts.validate_extracts import Check, check_forbidden_columns, check_ranges, check_small_cells


# ------------------------------------------------------------ statistics helpers

def test_wilson_ci_matches_published_value():
    # Newcombe (1998) worked example: 81 of 263 -> 0.2553 to 0.3662
    lo, hi = wilson_ci(81, 263)
    assert lo == pytest.approx(0.2553, abs=1e-4)
    assert hi == pytest.approx(0.3662, abs=1e-4)


def test_wilson_ci_stays_in_bounds_at_extremes():
    assert wilson_ci(0, 12)[0] == pytest.approx(0.0, abs=1e-12)
    assert wilson_ci(12, 12)[1] == pytest.approx(1.0, abs=1e-12)


def test_cramers_v_perfect_and_null_association():
    perfect = pd.DataFrame([[50, 0], [0, 50]])
    none = pd.DataFrame([[25, 25], [25, 25]])
    assert cramers_v(perfect) == pytest.approx(1.0)
    assert cramers_v(none) == pytest.approx(0.0)


@pytest.mark.parametrize("v,label", [(0.05, "negligible"), (0.2, "small"), (0.4, "medium"), (0.6, "large")])
def test_effect_labels(v, label):
    assert effect_label(v) == label


def test_design_matrix_drops_reference_and_names_dummies():
    spec = pd.DataFrame([
        {"factor": "dept", "kind": "categorical", "reference": "B", "factor_group": "workplace", "in_model": True, "label": "d"},
        {"factor": "ot", "kind": "binary", "reference": "", "factor_group": "workplace", "in_model": True, "label": "o"},
        {"factor": "skip", "kind": "categorical", "reference": "x", "factor_group": "workplace", "in_model": False, "label": "s"},
    ])
    df = pd.DataFrame({"dept": ["A", "B", "C", "B"], "ot": [1, 0, 1, 0], "skip": ["x", "y", "x", "y"]})
    X = design_matrix(df, spec)
    assert list(X.columns) == ["const", "dept=A", "dept=C", "ot"]
    assert X["dept=A"].tolist() == [1, 0, 0, 0]


def test_design_matrix_rejects_missing_reference():
    spec = pd.DataFrame([{"factor": "dept", "kind": "categorical", "reference": "Z",
                          "factor_group": "w", "in_model": True, "label": "d"}])
    with pytest.raises(ValueError):
        design_matrix(pd.DataFrame({"dept": ["A", "B"]}), spec)


def test_model_spec_is_consistent():
    spec = load_spec()
    assert spec["factor"].is_unique
    assert set(spec["kind"]) <= {"binary", "ordinal", "categorical"}
    assert set(spec["factor_group"]) <= {"workplace", "demographic"}
    cat = spec[spec["kind"] == "categorical"]
    assert (cat["reference"] != "").all(), "every categorical factor needs a reference level"


# ------------------------------------------------------------ extract validation gate

def test_gate_catches_unsuppressed_small_cell():
    ex = {"segs": pd.DataFrame({"headcount": [9, 50], "leavers": [3, 10], "attrition_rate": [0.33, 0.2]})}
    c = check_small_cells(ex, Check("P3", "small cells"))
    assert not c.passed and "expose leavers" in c.failures[0]


def test_gate_passes_suppressed_small_cell():
    ex = {"segs": pd.DataFrame({"headcount": [9, 50], "leavers": [np.nan, 10], "attrition_rate": [np.nan, 0.2]})}
    assert check_small_cells(ex, Check("P3", "small cells")).passed


def test_gate_catches_pay_and_id_columns():
    ex = {"a": pd.DataFrame({"employee_key": ["x"]}), "b": pd.DataFrame({"avg_monthly_income": [1]})}
    c = check_forbidden_columns(ex, Check("P2", "forbidden"))
    assert len(c.failures) == 2


def test_gate_catches_ci_not_containing_rate():
    ex = {"f": pd.DataFrame({"attrition_rate": [0.2], "ci_low": [0.25], "ci_high": [0.3]})}
    assert not check_ranges(ex, Check("Q1", "ranges")).passed


def test_gate_allows_odds_ratio_intervals_above_one():
    ex = {"or": pd.DataFrame({"odds_ratio": [5.7], "ci_low": [4.0], "ci_high": [8.2], "p_value": [0.001]})}
    assert check_ranges(ex, Check("Q1", "ranges")).passed
