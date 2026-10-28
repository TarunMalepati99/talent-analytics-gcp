"""Write reports/findings.md from the built marts and the local model mirror.

Every number in the report is queried from the warehouse at run time; nothing is
typed in by hand. Market-side sections are included only when real (non-fixture)
postings and JOLTS data have been loaded.

    python scripts/build_findings.py --db warehouse/talent.duckdb
"""

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd


def pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--model", default="reports/model_local_mirror.json")
    ap.add_argument("--stats", default="reports/stats")
    ap.add_argument("--out", default="reports/findings.md")
    args = ap.parse_args()
    con = duckdb.connect(args.db, read_only=True)
    q = lambda sql: con.sql(sql).fetchall()  # noqa: E731

    headcount, leavers, rate = q("""
        select count(*), sum(is_attrited::int), avg(is_attrited::int) from people_marts.dim_employee""")[0]

    drivers = q("""
        select factor, factor_level, headcount, attrition_rate, lift_vs_company
        from people_marts.mart_attrition_drivers
        where lift_vs_company is not null and headcount >= 30
        order by lift_vs_company desc limit 8""")

    interaction = q("""
        select tenure_band,
               sum(case when works_overtime then 1 else 0 end)                       as ot_n,
               avg(case when works_overtime then is_attrited::int end)              as ot_rate,
               sum(case when not works_overtime then 1 else 0 end)                   as no_ot_n,
               avg(case when not works_overtime then is_attrited::int end)          as no_ot_rate
        from people_marts.dim_employee group by 1 order by 1""")

    early = q("""
        select count(*), sum(is_attrited::int), avg(is_attrited::int)
        from people_marts.dim_employee
        where works_overtime and years_at_company <= 2""")[0]
    early_share_of_leavers = early[1] / leavers

    segments = q("""
        select department, job_role, tenure_band, headcount, attrition_rate
        from people_marts.fct_attrition_segments
        where not is_suppressed and attrition_rate >= 2 * (select avg(is_attrited::int) from people_marts.dim_employee)
        order by attrition_rate desc limit 6""")
    suppressed = q("select count(*), sum(headcount) from people_marts.fct_attrition_segments where is_suppressed")[0]

    real_postings = q("select count(*) from staging.stg_jobs__postings where not is_test_fixture")[0][0]
    jolts_rows = q("select count(*) from staging.stg_bls__jolts")[0][0]
    bench = q("select industry, benchmark_measure, through_month, benchmark_annual_rate, company_vs_benchmark_ratio "
              "from people_marts.mart_attrition_vs_benchmark order by industry, benchmark_measure") if jolts_rows else []
    pressure = q("select role_family, headcount, attrition_rate, lift_vs_company, market_open_postings, priority "
                 "from recruiting_marts.mart_replacement_pressure order by lift_vs_company desc nulls last") if real_postings else []

    model = json.loads(Path(args.model).read_text()) if Path(args.model).exists() else None
    stats_dir = Path(args.stats)
    sig = json.loads((stats_dir / "significance_summary.json").read_text()) if (stats_dir / "significance_summary.json").exists() else None
    xcheck = json.loads((stats_dir / "cross_check.json").read_text()) if (stats_dir / "cross_check.json").exists() else None

    L = []
    L.append(f"# Findings — Talent Analytics Platform\n\n_Generated {date.today().isoformat()} by `scripts/build_findings.py`._\n")
    L.append("> **Data caveat.** The HRIS layer uses IBM's public HR Analytics Employee Attrition dataset, which IBM "
             "describes as fictional. These findings demonstrate the pipeline and method; they are not facts about a real company.\n")

    L.append("## 1. Baseline\n")
    L.append(f"- {headcount:,} employees, {leavers} leavers → **company attrition {pct(rate)}**.\n")

    L.append("## 2. Strongest single drivers (lift vs company rate, groups ≥ 30 people)\n")
    L.append("| Factor | Level | Headcount | Attrition | Lift |\n|---|---|---:|---:|---:|")
    for f, lvl, n, r, lift in drivers:
        L.append(f"| {f} | {lvl} | {n} | {pct(r)} | {lift:.2f}× |")
    L.append("")

    L.append("## 3. The decision-grade finding: overtime × early tenure\n")
    L.append("| Tenure band | Overtime: n | Overtime: attrition | No overtime: n | No overtime: attrition |\n|---|---:|---:|---:|---:|")
    for band, ot_n, ot_r, no_n, no_r in interaction:
        L.append(f"| {band} | {ot_n} | {pct(ot_r)} | {no_n} | {pct(no_r)} |")
    L.append("")
    L.append(f"Employees with **≤ 2 years' tenure who work overtime** are {early[0]} people ({pct(early[0] / headcount)} of headcount) "
             f"but {early[1]} leavers (**{pct(early_share_of_leavers)} of all attrition**), leaving at {pct(early[2])}. "
             "Overtime matters at every tenure band, and the percentage-point gap is widest for new hires — the "
             "recommendation is an overtime cap / workload review for employees in their first two years, owned by HRBPs "
             "with the people managers of the segments below.\n")
    if sig:
        it = sig["overtime_x_early_tenure"]
        a, b = it["risk_gap_tenure_le_2y"], it["risk_gap_tenure_gt_2y"]
        L.append(f"**Is the effect really stronger for new hires?** On the absolute scale, yes: overtime adds "
                 f"{a['gap_pp']:.1f} percentage points (95% CI {a['gap_ci_low_pp']:.1f}–{a['gap_ci_high_pp']:.1f}) for ≤ 2 years' "
                 f"tenure vs {b['gap_pp']:.1f} (95% CI {b['gap_ci_low_pp']:.1f}–{b['gap_ci_high_pp']:.1f}) for longer tenure. On the "
                 f"odds scale, no: adjusted overtime odds ratios are {it['overtime_or_tenure_le_2y']['odds_ratio']:.1f} vs "
                 f"{it['overtime_or_tenure_gt_2y']['odds_ratio']:.1f}, and the interaction term is not significant "
                 f"(likelihood-ratio χ² = {it['lr_statistic']:.2f}, p = {it['p_value']:.2f}). Overtime multiplies risk by a similar "
                 "factor at every tenure; new hires lose more people from it because their baseline risk is higher. "
                 "That still makes them the place to act first, but the claim is about volume, not a special effect.\n")

    L.append(f"## 4. Segments leaving at ≥ 2× the company rate (department × role × tenure)\n")
    L.append("| Department | Role | Tenure | Headcount | Attrition |\n|---|---|---|---:|---:|")
    for d, jr, t, n, r in segments:
        L.append(f"| {d} | {jr} | {t} | {n} | {pct(r)} |")
    L.append(f"\n{suppressed[0]} small segments ({suppressed[1]} employees) are suppressed (fewer than 10 people) to prevent re-identification.\n")

    L.append("## 5. Which differences are statistically significant?\n")
    if sig:
        chi = pd.read_csv(stats_dir / "chi_square_tests.csv")
        ors = pd.read_csv(stats_dir / "logit_odds_ratios.csv")
        lr = sig["logistic_regression"]
        L.append(f"Chi-square tests on {sig['chi_square']['factors_tested']} factors, Benjamini–Hochberg adjusted: "
                 f"**{sig['chi_square']['significant_after_bh']} are significant** at α = {sig['alpha']}. "
                 f"Not significant: {', '.join(sig['chi_square']['not_significant'])}.\n")
        L.append("| Factor | Group | χ² (df) | Adjusted p | Cramér's V |\n|---|---|---:|---:|---:|")
        for _, r in chi.head(8).iterrows():
            L.append(f"| {r['label']} | {r['factor_group']} | {r['chi2']:.1f} ({r['dof']}) | {r['p_adj_bh']:.1e} | {r['cramers_v']:.2f} ({r['effect_size']}) |")
        L.append("")
        L.append(f"Multivariable logistic regression ({lr['parameters']} terms, McFadden pseudo-R² {lr['mcfadden_pseudo_r2']:.2f}); "
                 "strongest adjusted odds ratios, 95% CI:\n")
        L.append("| Term | Odds ratio | 95% CI | p |\n|---|---:|---|---:|")
        top = ors[ors["significant"]].assign(dist=lambda d: (d["odds_ratio"].apply(lambda x: abs(__import__("math").log(x))))).sort_values("dist", ascending=False).head(8)
        for _, r in top.iterrows():
            L.append(f"| {r['term']} | {r['odds_ratio']:.2f} | {r['ci_low']:.2f}–{r['ci_high']:.2f} | {r['p_value']:.1e} |")
        L.append("")
        stalled = ors[ors["term"] == "is_promotion_stalled"]
        chi_stalled = chi[chi["factor"] == "is_promotion_stalled"]
        if not stalled.empty and not chi_stalled.empty and stalled.iloc[0]["significant"] and not chi_stalled.iloc[0]["significant_bh"]:
            L.append(f"Promotion stall shows why adjustment matters: on its own it isn't linked to attrition "
                     f"(adjusted p = {chi_stalled.iloc[0]['p_adj_bh']:.2f}), but holding tenure and level constant it raises the odds "
                     f"of leaving {stalled.iloc[0]['odds_ratio']:.1f}× — stalled employees tend to be long-tenured, which hides the effect.\n")
        L.append(f"Demographics are in the regression as controls only; the scoring model excludes them. "
                 f"Events per parameter: {lr['events_per_parameter']} (guideline ≈ 10), so small levels have wide intervals.\n")
        if xcheck:
            L.append(f"**Replication:** an independent base-R implementation was cross-checked against Python: "
                     f"**{xcheck['status']}**" + (f" on {xcheck['values_compared']} values" if xcheck.get('values_compared') else "") + ".\n")
    else:
        L.append("Run `make stats` first.\n")

    L.append("## 6. Attrition-risk model (local mirror of the BigQuery ML model)\n")
    if model:
        m = model["metrics"]
        L.append(f"- Logistic regression, class-balanced, protected attributes excluded from features; "
                 f"{m['train_rows']} train / {m['eval_rows']} held-out employees.")
        L.append(f"- Held-out **ROC AUC {m['roc_auc']}**, recall {m['recall_at_0_5']} and precision {m['precision_at_0_5']} at a 0.5 threshold.")
        L.append(f"- {model['high_risk_employees']} of {model['current_employees_scored']} current employees score ≥ {model['high_risk_threshold']} (high risk).")
        L.append("- **Fairness gate (four-fifths rule on high-risk flags):**")
        for attr, res in model["fairness_audit"].items():
            verdict = "pass" if res["passes_four_fifths"] else "**FAIL**"
            L.append(f"  - {attr}: adverse-impact ratio {res['adverse_impact_ratio']} → {verdict}")
        failed = [a for a, r in model["fairness_audit"].items() if r["passes_four_fifths"] is False]
        if failed:
            detail = []
            for a in failed:
                g = model["fairness_audit"][a]["groups"]
                hi, lo = max(g, key=lambda k: g[k]["flag_rate"]), min(g, key=lambda k: g[k]["flag_rate"])
                detail.append(f"{a} '{hi}' is flagged {pct(g[hi]['flag_rate'])} of the time vs {pct(g[lo]['flag_rate'])} for '{lo}'")
            L.append(f"\nThe gate fails: {'; '.join(detail)}. Protected attributes are not features, so this comes through "
                     "proxies such as tenure and job level. In the Composer DAG this check blocks "
                     "`publish_segment_risk`, so HRBPs would get the descriptive marts above but not model scores until "
                     "the proxy issue is addressed (e.g. dropping or constraining proxy features, or per-group thresholds reviewed with legal).")
        L.append("\n_Numbers from BigQuery ML itself will differ somewhat (different split hash and optimizer)._\n")
    else:
        L.append("Run `python bqml/local_mirror.py` first.\n")

    L.append("## 7. External benchmark (BLS JOLTS)\n")
    if bench:
        L.append("| Industry | Measure | Through | Annual rate | Company ÷ benchmark |\n|---|---|---|---:|---:|")
        for ind, meas, thru, br, ratio in bench:
            L.append(f"| {ind} | {meas} | {thru} | {pct(br)} | {ratio:.2f} |")
        L.append("\nAssumes the HRIS attrition flag covers a 12-month window (IBM does not document it).\n")
    else:
        L.append("Not loaded in this run. `make ingest` pulls live JOLTS data from the BLS API.\n")

    L.append("## 8. Replacement pressure (internal attrition × market demand)\n")
    if pressure:
        L.append("| Role family | Headcount | Attrition | Lift | Open market postings | Priority |\n|---|---:|---:|---:|---:|---|")
        for rf, n, r, lift, mk, pr in pressure:
            L.append(f"| {rf} | {n} | {pct(r)} | {'n/a' if lift is None else f'{lift:.2f}×'} | {mk} | {pr} |")
        L.append("")
    else:
        L.append("Only offline test fixtures are loaded, so this section is left out. `make ingest` pulls live postings "
                 "from the Greenhouse/Lever boards in `config/boards.yaml`.\n")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(L))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
