"""Forest plot of adjusted odds ratios -> reports/figures/adjusted_odds_ratios.png

One row per model term, point = odds ratio, whisker = 95% CI, log scale with a
reference line at 1 (no effect). Significant terms are filled, others hollow and
grey, so the encoding doesn't rely on colour alone.

    python analysis/plot_odds_ratios.py
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

INK, MUTED, GRID, SURFACE, SERIES = "#0b0b0b", "#8a8984", "#e4e3df", "#fcfcfb", "#2a78d6"


def label(r) -> str:
    if r["level"] in ("Yes", "per point"):
        return r["factor"].replace("_", " ") + (" (per point)" if r["level"] == "per point" else "")
    return f"{r['factor'].replace('_', ' ')}: {r['level']}  (vs {r['reference']})"


def main(src="reports/stats/logit_odds_ratios.csv", out="reports/figures/adjusted_odds_ratios.png"):
    df = pd.read_csv(src).sort_values("odds_ratio").reset_index(drop=True)
    df["name"] = df.apply(label, axis=1)

    fig, ax = plt.subplots(figsize=(9, 0.32 * len(df) + 1.6), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for i, r in df.iterrows():
        sig = r["significant"]
        color = SERIES if sig else MUTED
        ax.plot([r["ci_low"], r["ci_high"]], [i, i], color=color, lw=2, solid_capstyle="round")
        ax.scatter(r["odds_ratio"], i, s=46, zorder=3, color=color if sig else SURFACE,
                   edgecolor=color, linewidth=2)
    ax.axvline(1, color=INK, lw=1)
    ax.set_xscale("log")
    ax.set_xticks([0.25, 0.5, 1, 2, 4, 8, 16])
    ax.set_xticklabels(["0.25", "0.5", "1", "2", "4", "8", "16"])
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["name"], fontsize=8, color=INK)
    ax.tick_params(axis="x", labelsize=8, colors="#52514e")
    ax.grid(axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    for s in ("top", "right", "left"):
        ax.spines[s].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.set_xlabel("Adjusted odds ratio of leaving (log scale; 1 = no effect)", fontsize=9, color="#52514e")
    ax.set_title("What predicts attrition, holding other factors constant", loc="left", fontsize=11, color=INK, pad=24)
    ax.text(0, 1.01, "Filled = significant at p < 0.05 · hollow grey = not significant · bars = 95% CI · "
            "IBM sample HR data (fictional)", transform=ax.transAxes, fontsize=7.5, color="#52514e")
    fig.tight_layout()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
