# Retention brief — what's driving attrition and what to do first

_Generated 2026-10-28 · audience: HR leadership and people managers · data: IBM's sample HR dataset (fictional), used to demonstrate the method._

## The short version

About **1 in 6 employees left (16%)**, above the 12% placeholder target. Among people in their first two years it is **30%**. The single biggest lever is **overtime**: people working overtime have about **6× the odds of leaving** of comparable colleagues who don't, even after accounting for level, tenure, travel, department, stock options, satisfaction and demographics.

## What we found

1. **Overtime matters at every career stage, and costs the most people early on.** For employees in their first two years, 51% of those working overtime left, against 21% of those who didn't — a gap of 30 percentage points. For longer-tenured staff the gap is 16 points. Overtime raises the odds of leaving by a similar multiple at both stages; the gap is wider for new hires because more of them leave to begin with.
2. **30% of employees in their first two years work overtime** (placeholder KPI target 20%).
3. **Frequent travel and entry-level roles also stand out.** Frequent travellers have about 2.4× the odds of leaving of those who travel rarely; job level 1 about 3.6× the odds of level 2.
4. **Engagement scores predict exits.** Each one-point rise in job satisfaction (on a 1–4 scale) lowers the odds of leaving by about 31%.
5. **Sales has the highest department attrition (21%).**

## Recommended actions

1. Cap or review overtime for employees in their first two years; start with the departments where new-hire overtime is highest (see the KPI scorecard).
2. Add a 90-day and 12-month stay interview for entry-level and frequently travelling staff.
3. Track the new-hire overtime KPI monthly alongside early-tenure attrition to see whether the change works.

## How sure are we?

- 13 of 17 factors show a statistically significant link to attrition after correcting for testing many factors at once.
- Every figure was checked twice: the statistics were computed independently in Python and R and agree on all 178 compared values, and the dashboard extracts reconcile to the warehouse (see `reports/validation_report.md`).
- These are associations in one snapshot, not proof that overtime *causes* exits. A pilot with a comparison group is the way to confirm the effect before scaling a policy.
- Groups under 10 people are not reported, to protect privacy.
