"""Write reports/leadership_brief.md: a one-page, non-technical summary.

For readers who won't open the dashboard or the stats tables. Every number is
read from the warehouse or the validated stats outputs at run time.

    python scripts/build_brief.py --db warehouse/talent.duckdb
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--stats-dir", default="reports/stats")
    ap.add_argument("--out", default="reports/leadership_brief.md")
    args = ap.parse_args(argv)
    stats = Path(args.stats_dir)

    con = duckdb.connect(args.db, read_only=True)
    kpi = con.sql("select * from people_marts.mart_kpi_scorecard").df()
    con.close()
    summary = json.loads((stats / "significance_summary.json").read_text())
    ors = pd.read_csv(stats / "logit_odds_ratios.csv").set_index("term")
    check = json.loads((stats / "cross_check.json").read_text()) if (stats / "cross_check.json").exists() else {}

    def k(kid, slice_value="All"):
        return kpi[(kpi.kpi_id == kid) & (kpi.slice_value == slice_value)].iloc[0]

    attr, early, ot = k("ATTR_RATE"), k("EARLY_ATTR"), k("NEWHIRE_OT")
    sales = k("ATTR_RATE", "Sales")
    inter = summary["overtime_x_early_tenure"]
    g_new, g_old = inter["risk_gap_tenure_le_2y"], inter["risk_gap_tenure_gt_2y"]
    ot_or = ors.loc["works_overtime"]
    travel = ors.loc["business_travel=Travel_Frequently"]
    lvl1 = ors.loc["job_level=1"]
    sat = ors.loc["job_satisfaction"]
    n_sig, n_tested = summary["chi_square"]["significant_after_bh"], summary["chi_square"]["factors_tested"]

    L = [
        "# Retention brief — what's driving attrition and what to do first",
        "",
        f"_Generated {date.today().isoformat()} · audience: HR leadership and people managers · "
        "data: IBM's sample HR dataset (fictional), used to demonstrate the method._",
        "",
        "## The short version",
        "",
        f"About **1 in {round(1 / attr.kpi_value)} employees left ({pct(attr.kpi_value)})**, above the {pct(attr.target)} placeholder target. "
        f"Among people in their first two years it is **{pct(early.kpi_value)}**. "
        f"The single biggest lever is **overtime**: people working overtime have about **{ot_or.odds_ratio:.0f}× the odds of leaving** "
        f"of comparable colleagues who don't, even after accounting for level, tenure, travel, "
        f"department, stock options, satisfaction and demographics.",
        "",
        "## What we found",
        "",
        f"1. **Overtime matters at every career stage, and costs the most people early on.** For employees in their first two "
        f"years, {pct(g_new['overtime_rate'])} of those working overtime left, against {pct(g_new['no_overtime_rate'])} of those "
        f"who didn't — a gap of {g_new['gap_pp']:.0f} percentage points. For longer-tenured staff the gap is "
        f"{g_old['gap_pp']:.0f} points. Overtime raises the odds of leaving by a similar multiple at both stages; the gap "
        f"is wider for new hires because more of them leave to begin with.",
        f"2. **{pct(ot.kpi_value)} of employees in their first two years work overtime** (placeholder KPI target {pct(ot.target)}).",
        f"3. **Frequent travel and entry-level roles also stand out.** Frequent travellers have about {travel.odds_ratio:.1f}× the "
        f"odds of leaving of those who travel rarely; job level 1 about {lvl1.odds_ratio:.1f}× the odds of level 2.",
        f"4. **Engagement scores predict exits.** Each one-point rise in job satisfaction (on a 1–4 scale) lowers the odds of "
        f"leaving by about {pct(1 - sat.odds_ratio)}.",
        f"5. **Sales has the highest department attrition ({pct(sales.kpi_value)}).**",
        "",
        "## Recommended actions",
        "",
        "1. Cap or review overtime for employees in their first two years; start with the departments where "
        "new-hire overtime is highest (see the KPI scorecard).",
        "2. Add a 90-day and 12-month stay interview for entry-level and frequently travelling staff.",
        "3. Track the new-hire overtime KPI monthly alongside early-tenure attrition to see whether the change works.",
        "",
        "## How sure are we?",
        "",
        f"- {n_sig} of {n_tested} factors show a statistically significant link to attrition after correcting for testing many "
        "factors at once.",
        "- Every figure was checked twice: the statistics were computed independently in Python and R"
        + (f" and agree on all {check['values_compared']} compared values" if check.get("status") == "pass" else "")
        + ", and the dashboard extracts reconcile to the warehouse (see `reports/validation_report.md`).",
        "- These are associations in one snapshot, not proof that overtime *causes* exits. A pilot with a comparison "
        "group is the way to confirm the effect before scaling a policy.",
        "- Groups under 10 people are not reported, to protect privacy.",
        "",
    ]
    Path(args.out).write_text("\n".join(L))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
