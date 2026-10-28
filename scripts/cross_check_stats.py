"""Check that the Python and R implementations of the significance analysis agree.

Two independent implementations (statsmodels/scipy vs base R glm/chisq.test),
each coding the factors from the spec on its own. If they disagree beyond
numerical tolerance, something is wrong in one of them, and this exits non-zero
so the build stops before any report is written from the numbers.

    python scripts/cross_check_stats.py --stats-dir reports/stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

TOL_REL = 1e-4   # relative tolerance for statistics and odds ratios
TOL_P = 1e-6     # absolute tolerance for p-values


def rel_diff(a: pd.Series, b: pd.Series) -> float:
    return float(((a - b).abs() / b.abs().clip(lower=1e-12)).max())


def compare(stats_dir: Path) -> dict:
    py_chi = pd.read_csv(stats_dir / "chi_square_tests.csv").set_index("factor")
    r_chi = pd.read_csv(stats_dir / "r_chi_square_tests.csv").set_index("factor")
    py_or = pd.read_csv(stats_dir / "logit_odds_ratios.csv").set_index("term")
    r_or = pd.read_csv(stats_dir / "r_logit_odds_ratios.csv").set_index("term")
    py_int = json.loads((stats_dir / "significance_summary.json").read_text())["overtime_x_early_tenure"]
    r_int = pd.read_csv(stats_dir / "r_interaction_test.csv").iloc[0]

    problems = []
    if set(py_chi.index) != set(r_chi.index):
        problems.append(f"chi-square factors differ: {sorted(set(py_chi.index) ^ set(r_chi.index))}")
    if set(py_or.index) != set(r_or.index):
        problems.append(f"model terms differ: {sorted(set(py_or.index) ^ set(r_or.index))}")
    if problems:
        return {"status": "fail", "problems": problems}

    r_chi, r_or = r_chi.loc[py_chi.index], r_or.loc[py_or.index]
    diffs = {
        "chi2_max_rel_diff": rel_diff(py_chi["chi2"], r_chi["chi2"]),
        "dof_mismatches": int((py_chi["dof"] != r_chi["dof"]).sum()),
        "chi_p_adj_max_abs_diff": float((py_chi["p_adj_bh"] - r_chi["p_adj_bh"]).abs().max()),
        "cramers_v_max_rel_diff": rel_diff(py_chi["cramers_v"], r_chi["cramers_v"]),
        "odds_ratio_max_rel_diff": rel_diff(py_or["odds_ratio"], r_or["odds_ratio"]),
        "or_ci_max_rel_diff": max(rel_diff(py_or["ci_low"], r_or["ci_low"]), rel_diff(py_or["ci_high"], r_or["ci_high"])),
        "or_p_max_abs_diff": float((py_or["p_value"] - r_or["p_value"]).abs().max()),
        "interaction_lr_rel_diff": abs(py_int["lr_statistic"] - r_int["lr_statistic"]) / abs(r_int["lr_statistic"]),
        "interaction_p_abs_diff": abs(py_int["p_value"] - r_int["p_value"]),
    }
    checks = {
        "chi2_max_rel_diff": TOL_REL, "cramers_v_max_rel_diff": TOL_REL, "odds_ratio_max_rel_diff": TOL_REL,
        "or_ci_max_rel_diff": TOL_REL, "interaction_lr_rel_diff": TOL_REL,
        "chi_p_adj_max_abs_diff": TOL_P, "or_p_max_abs_diff": TOL_P, "interaction_p_abs_diff": TOL_P,
    }
    problems = [f"{k} = {diffs[k]:.3g} exceeds {tol:g}" for k, tol in checks.items() if diffs[k] > tol]
    if diffs["dof_mismatches"]:
        problems.append(f"{diffs['dof_mismatches']} degrees-of-freedom mismatches")
    return {
        "status": "pass" if not problems else "fail",
        "values_compared": int(len(py_chi) * 4 + len(py_or) * 4 + 2),
        "tolerances": {"relative": TOL_REL, "p_value_absolute": TOL_P},
        "max_differences": diffs,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stats-dir", default="reports/stats")
    args = ap.parse_args(argv)
    d = Path(args.stats_dir)
    if not (d / "r_logit_odds_ratios.csv").exists():
        result = {"status": "not_run", "problems": ["R outputs missing: install R and run `make stats`"]}
    else:
        result = compare(d)
    (d / "cross_check.json").write_text(json.dumps(result, indent=2))
    print(f"Python vs R cross-check: {result['status']}")
    for p in result.get("problems", []):
        print(f"  - {p}")
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
