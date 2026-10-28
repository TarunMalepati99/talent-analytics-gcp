"""Local mirror of the BigQuery ML attrition model, for offline development.

Same features, same exclusions (no age/gender/marital status as features), same
class balancing and an 80/20 split by hashed employee key. It is NOT the BQML
model: BigQuery uses FARM_FINGERPRINT for the split and its own optimizer, so
numbers will differ somewhat. Use it to sanity-check features and the fairness
audit before paying for a BigQuery run.

    python bqml/local_mirror.py --db warehouse/talent.duckdb --out reports/model_local_mirror.json
"""

import argparse
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

CATEGORICAL = ["department", "job_role", "job_level", "business_travel", "pay_quartile_in_level", "stock_option_level", "works_overtime"]
NUMERIC = ["years_at_company", "years_since_last_promotion", "job_satisfaction", "environment_satisfaction", "work_life_balance"]
HIGH_RISK = 0.70
MIN_CELL = 10


def load(db: str) -> pd.DataFrame:
    con = duckdb.connect(db, read_only=True)
    df = con.sql("select * from people_marts.dim_employee").df()
    con.close()
    for c in ["job_level", "pay_quartile_in_level", "stock_option_level", "works_overtime"]:
        df[c] = df[c].astype(str)
    df["is_eval"] = df["employee_key"].map(lambda k: int(hashlib.md5(k.encode()).hexdigest(), 16) % 5 == 0)
    return df


def adverse_impact(scored: pd.DataFrame, attribute: str) -> dict:
    g = scored.groupby(attribute).agg(n=("high", "size"), flag_rate=("high", "mean"))
    g = g[g["n"] >= MIN_CELL]
    ratio = float(g["flag_rate"].min() / g["flag_rate"].max()) if g["flag_rate"].max() > 0 else None
    return {
        "adverse_impact_ratio": None if ratio is None else round(ratio, 3),
        "passes_four_fifths": None if ratio is None else ratio >= 0.8,
        "groups": {str(k): {"n": int(v.n), "flag_rate": round(float(v.flag_rate), 3)} for k, v in g.iterrows()},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="warehouse/talent.duckdb")
    ap.add_argument("--out", default="reports/model_local_mirror.json")
    args = ap.parse_args()

    df = load(args.db)
    train, test = df[~df.is_eval], df[df.is_eval]
    X_cols = CATEGORICAL + NUMERIC

    model = Pipeline([
        ("prep", ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("num", StandardScaler(), NUMERIC),
        ])),
        ("lr", LogisticRegression(class_weight="balanced", C=1.0, max_iter=2000)),
    ])
    model.fit(train[X_cols], train["is_attrited"])

    p_test = model.predict_proba(test[X_cols])[:, 1]
    y_test = test["is_attrited"].astype(int)
    metrics = {
        "train_rows": int(len(train)), "eval_rows": int(len(test)),
        "eval_positive_rate": round(float(y_test.mean()), 3),
        "roc_auc": round(float(roc_auc_score(y_test, p_test)), 3),
        "precision_at_0_5": round(float(precision_score(y_test, p_test >= 0.5)), 3),
        "recall_at_0_5": round(float(recall_score(y_test, p_test >= 0.5)), 3),
    }

    names = model.named_steps["prep"].get_feature_names_out()
    coefs = model.named_steps["lr"].coef_[0]
    top = sorted(zip(names, coefs), key=lambda t: -abs(t[1]))[:12]

    # Score current employees and audit outputs by protected attributes (not used as features).
    current = df[~df.is_attrited].copy()
    current["prob"] = model.predict_proba(current[X_cols])[:, 1]
    current["high"] = current["prob"] >= HIGH_RISK
    fairness = {attr: adverse_impact(current, attr) for attr in ["gender", "age_band"]}

    report = {
        "note": "Local scikit-learn mirror of bqml/01_train_attrition_model.sql; not BigQuery ML output.",
        "metrics": metrics,
        "top_coefficients": [{"feature": n.split("__", 1)[1], "coef": round(float(c), 3)} for n, c in top],
        "current_employees_scored": int(len(current)),
        "high_risk_threshold": HIGH_RISK,
        "high_risk_employees": int(current["high"].sum()),
        "fairness_audit": fairness,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    np.random.seed(0)
    main()
