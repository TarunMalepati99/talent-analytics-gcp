"""Statistical significance layer: which differences in attrition are real, and how large are they?

The marts show *where* attrition is high. This script tests whether those gaps are
statistically significant and estimates each factor's effect while holding the
others constant, so a reader can tell a real driver from noise in a small group.

1. Chi-square test of independence for every factor in analysis/model_spec.csv
   (workplace and demographic), with Cramér's V as the effect size and a
   Benjamini-Hochberg correction because many factors are tested at once.
2. Attrition rate per factor level with a Wilson 95% confidence interval
   (levels under the minimum cell size are suppressed, as in the marts).
3. Multivariable logistic regression -> adjusted odds ratios with 95% CIs.
   Demographics are included here as *controls* for inference. This is different
   from the scoring model in bqml/, which excludes them as features by design.
4. A likelihood-ratio test of the overtime x early-tenure interaction, the
   project's headline finding.

The same analysis is re-implemented independently in R (analysis/r/) and
scripts/cross_check_stats.py checks the two agree before anything is published.

    python analysis/attrition_significance.py --db warehouse/talent.duckdb
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import chi2, chi2_contingency, norm
from statsmodels.stats.multitest import multipletests

SPEC_PATH = Path(__file__).with_name("model_spec.csv")
MIN_CELL = 10
ALPHA = 0.05
EARLY_TENURE_YEARS = 2


def load_spec(path: Path = SPEC_PATH) -> pd.DataFrame:
    spec = pd.read_csv(path, dtype=str, keep_default_na=False)
    spec["in_model"] = spec["in_model"] == "1"
    return spec


def load_base(db: str, spec: pd.DataFrame) -> pd.DataFrame:
    """One row per employee: the outcome, tenure in years, and every factor in the spec."""
    con = duckdb.connect(db, read_only=True)
    cols = ", ".join(["is_attrited", "years_at_company"] + list(spec["factor"]))
    df = con.sql(f"select {cols} from people_marts.dim_employee").df()
    con.close()
    df["is_attrited"] = df["is_attrited"].astype(int)
    for _, row in spec.iterrows():
        f = row["factor"]
        if row["kind"] == "binary":
            df[f] = df[f].astype(int)
        elif row["kind"] == "ordinal":
            df[f] = df[f].astype(int)
        else:
            df[f] = df[f].astype(str)
    return df


# ---------------------------------------------------------------- helpers

def cramers_v(table: pd.DataFrame) -> float:
    stat = chi2_contingency(table, correction=False)[0]
    n = table.to_numpy().sum()
    k = min(table.shape) - 1
    return float(np.sqrt(stat / (n * k))) if k > 0 else float("nan")


def effect_label(v: float) -> str:
    if v < 0.10:
        return "negligible"
    if v < 0.30:
        return "small"
    if v < 0.50:
        return "medium"
    return "large"


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n == 0:
        return float("nan"), float("nan")
    p = k / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return float(centre - half), float(centre + half)


# ---------------------------------------------------------------- 1. chi-square

def chi_square_tests(df: pd.DataFrame, spec: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, s in spec.iterrows():
        table = pd.crosstab(df[s["factor"]], df["is_attrited"])
        stat, p, dof, expected = chi2_contingency(table, correction=False)
        v = cramers_v(table)
        rows.append({
            "factor": s["factor"], "label": s["label"], "factor_group": s["factor_group"],
            "levels": int(table.shape[0]), "n": int(table.to_numpy().sum()),
            "chi2": float(stat), "dof": int(dof), "p_value": float(p),
            "cramers_v": v, "effect_size": effect_label(v),
            "min_expected_count": float(expected.min()),
            "share_cells_expected_lt5": float((expected < 5).mean()),
        })
    out = pd.DataFrame(rows)
    out["p_adj_bh"] = multipletests(out["p_value"], alpha=ALPHA, method="fdr_bh")[1]
    out["significant_bh"] = out["p_adj_bh"] < ALPHA
    return out.sort_values("cramers_v", ascending=False).reset_index(drop=True)


# ---------------------------------------------------------------- 2. rates + CIs

def rates_with_ci(df: pd.DataFrame, spec: pd.DataFrame) -> pd.DataFrame:
    company = df["is_attrited"].mean()
    rows = []
    for _, s in spec.iterrows():
        g = df.groupby(df[s["factor"]].astype(str))["is_attrited"].agg(["size", "sum"])
        for level, r in g.iterrows():
            n, k = int(r["size"]), int(r["sum"])
            suppressed = n < MIN_CELL
            lo, hi = wilson_ci(k, n)
            rows.append({
                "factor": s["factor"], "label": s["label"], "factor_group": s["factor_group"],
                "factor_level": level,
                "level_label": {"1": "Yes", "0": "No"}.get(level, level) if s["kind"] == "binary" else level,
                "headcount": n, "is_suppressed": suppressed,
                "leavers": None if suppressed else k,
                "attrition_rate": None if suppressed else k / n,
                "ci_low": None if suppressed else lo,
                "ci_high": None if suppressed else hi,
                "company_rate": company,
                # CI entirely above / below the company rate: a gap a reader can act on.
                "vs_company": None if suppressed else ("above" if lo > company else "below" if hi < company else "within"),
            })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 3. logistic regression

def design_matrix(df: pd.DataFrame, spec: pd.DataFrame) -> pd.DataFrame:
    """Explicit dummy coding so the column names ('factor=level') match the R replication."""
    X = pd.DataFrame({"const": 1.0}, index=df.index)
    for _, s in spec[spec["in_model"]].iterrows():
        f = s["factor"]
        if s["kind"] in ("binary", "ordinal"):
            X[f] = df[f].astype(float)
            continue
        levels = sorted(df[f].unique())
        if s["reference"] not in levels:
            raise ValueError(f"reference '{s['reference']}' not found in {f}: {levels}")
        for lvl in levels:
            if lvl != s["reference"]:
                X[f"{f}={lvl}"] = (df[f] == lvl).astype(float)
    return X


def term_meta(term: str, spec: pd.DataFrame) -> tuple[str, str, str]:
    factor = term.split("=", 1)[0]
    row = spec[spec["factor"] == factor]
    if row.empty:
        return factor, "", ""
    r = row.iloc[0]
    level = term.split("=", 1)[1] if "=" in term else ("per point" if r["kind"] == "ordinal" else "Yes")
    ref = r["reference"] if r["kind"] == "categorical" else ("1 point lower" if r["kind"] == "ordinal" else "No")
    return factor, level, ref


def odds_ratio_table(fit, spec: pd.DataFrame) -> pd.DataFrame:
    z = norm.ppf(1 - ALPHA / 2)
    rows = []
    for term in fit.params.index:
        if term == "const":
            continue
        b, se, p = fit.params[term], fit.bse[term], fit.pvalues[term]
        factor, level, ref = term_meta(term, spec)
        grp = spec.set_index("factor")["factor_group"].get(factor, "interaction")
        rows.append({
            "term": term, "factor": factor, "factor_group": grp, "level": level, "reference": ref,
            "coef": float(b), "std_err": float(se),
            "odds_ratio": float(np.exp(b)), "ci_low": float(np.exp(b - z * se)), "ci_high": float(np.exp(b + z * se)),
            "p_value": float(p), "significant": bool(p < ALPHA),
        })
    return pd.DataFrame(rows)


def fit_logit(X: pd.DataFrame, y: pd.Series):
    fit = sm.Logit(y, X).fit(disp=0, maxiter=200, method="newton")
    if not fit.mle_retvals.get("converged", False):
        raise RuntimeError("logistic regression did not converge")
    return fit


def interaction_test(df: pd.DataFrame, X: pd.DataFrame, base_fit) -> dict:
    """Does overtime hurt early-tenure staff more? Likelihood-ratio test of the interaction term."""
    early = (df["years_at_company"] <= EARLY_TENURE_YEARS).astype(float)
    Xi = X.copy()
    Xi["works_overtime:early_tenure"] = X["works_overtime"] * early
    full = fit_logit(Xi, df["is_attrited"])
    lr = 2 * (full.llf - base_fit.llf)
    p = float(chi2.sf(lr, 1))

    z = norm.ppf(1 - ALPHA / 2)
    b_ot, b_int = full.params["works_overtime"], full.params["works_overtime:early_tenure"]
    cov = full.cov_params()
    se_early = float(np.sqrt(cov.loc["works_overtime", "works_overtime"]
                             + cov.loc["works_overtime:early_tenure", "works_overtime:early_tenure"]
                             + 2 * cov.loc["works_overtime", "works_overtime:early_tenure"]))
    se_later = float(full.bse["works_overtime"])

    # The same question on the absolute scale (percentage points), which is what a
    # manager budgets against: an equal odds ratio is a bigger gap where risk is higher.
    def risk_gap(mask: pd.Series) -> dict:
        ot, no = df[mask & (df["works_overtime"] == 1)], df[mask & (df["works_overtime"] == 0)]
        p1, p0 = ot["is_attrited"].mean(), no["is_attrited"].mean()
        se = np.sqrt(p1 * (1 - p1) / len(ot) + p0 * (1 - p0) / len(no))
        return {"overtime_rate": float(p1), "no_overtime_rate": float(p0), "gap_pp": float((p1 - p0) * 100),
                "gap_ci_low_pp": float((p1 - p0 - z * se) * 100), "gap_ci_high_pp": float((p1 - p0 + z * se) * 100),
                "n_overtime": int(len(ot)), "n_no_overtime": int(len(no))}

    early_mask = df["years_at_company"] <= EARLY_TENURE_YEARS
    return {
        "lr_statistic": float(lr), "df": 1, "p_value": p, "significant": p < ALPHA,
        "interaction_odds_ratio": float(np.exp(b_int)),
        "overtime_or_tenure_gt_2y": {"odds_ratio": float(np.exp(b_ot)),
                                     "ci_low": float(np.exp(b_ot - z * se_later)), "ci_high": float(np.exp(b_ot + z * se_later))},
        "overtime_or_tenure_le_2y": {"odds_ratio": float(np.exp(b_ot + b_int)),
                                     "ci_low": float(np.exp(b_ot + b_int - z * se_early)),
                                     "ci_high": float(np.exp(b_ot + b_int + z * se_early))},
        "risk_gap_tenure_le_2y": risk_gap(early_mask),
        "risk_gap_tenure_gt_2y": risk_gap(~early_mask),
    }


# ---------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--out-dir", default="reports/stats")
    ap.add_argument("--r-input", default="warehouse/analysis_base.csv",
                    help="employee-grain extract for the R replication; kept in the git-ignored warehouse/ folder")
    args = ap.parse_args(argv)

    spec = load_spec()
    df = load_base(args.db, spec)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Employee-level rows never go to reports/: only to the local warehouse folder for R.
    Path(args.r_input).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.r_input, index=False)

    chi = chi_square_tests(df, spec)
    chi.to_csv(out / "chi_square_tests.csv", index=False)

    rates = rates_with_ci(df, spec)
    rates.to_csv(out / "attrition_rates_ci.csv", index=False)

    X = design_matrix(df, spec)
    fit = fit_logit(X, df["is_attrited"])
    ors = odds_ratio_table(fit, spec)
    ors.to_csv(out / "logit_odds_ratios.csv", index=False)

    inter = interaction_test(df, X, fit)
    n_params = X.shape[1] - 1
    events = int(df["is_attrited"].sum())
    summary = {
        "n_employees": int(len(df)),
        "n_leavers": events,
        "alpha": ALPHA,
        "chi_square": {
            "factors_tested": int(len(chi)),
            "significant_after_bh": int(chi["significant_bh"].sum()),
            "not_significant": chi.loc[~chi["significant_bh"], "factor"].tolist(),
        },
        "logistic_regression": {
            "parameters": int(n_params),
            "events_per_parameter": round(events / n_params, 1),
            "converged": True,
            "log_likelihood": float(fit.llf),
            "mcfadden_pseudo_r2": float(fit.prsquared),
            "aic": float(fit.aic),
            "llr_p_value": float(fit.llr_pvalue),
            "significant_terms": int(ors["significant"].sum()),
        },
        "overtime_x_early_tenure": inter,
    }
    (out / "significance_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"wrote {out}/chi_square_tests.csv, attrition_rates_ci.csv, logit_odds_ratios.csv, significance_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
