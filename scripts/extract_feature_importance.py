"""
Gain-based feature importance per taxonomic rank for both models.

XGBoost: the model's six categorical features are the ranks themselves.
Entity Embeddings: the Stage 2 booster sees 84 embedding dimensions (f0..f83);
their gains are summed per rank block using emb_dims from metrics_ee.json.
Both are normalised to 100%.  Note the EE aggregation is biased toward ranks
with more embedding dimensions (kingdom 4 .. genus 32).

Outputs (predictive_models/results/):
  tab_feature_importance.tex      Entity Embeddings only (main supplement)
  tab_feature_importance_cmp.tex  both models
  feature_importance.png          grouped bars, both models
  feature_importance.json         the percentages (for make_numbers_tex.py)

Run from repo root:
  predictive_models/.venv/bin/python scripts/extract_feature_importance.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _results_common import (  # noqa: E402
    ARTIFACTS,
    METHOD_TITLE,
    METHODS,
    MODEL_FEATURES,
    RESULTS,
    read_json,
    write_json,
    write_tex,
)

HIER = MODEL_FEATURES  # kingdom .. genus


def xgb_gain_by_rank() -> dict[str, float]:
    booster = xgb.Booster()
    booster.load_model(str(ARTIFACTS / "model.ubj"))
    scores = booster.get_score(importance_type="gain")
    total = sum(scores.values())
    return {r: 100.0 * scores.get(r, 0.0) / total for r in HIER}


def ee_gain_by_rank() -> dict[str, float]:
    emb_dims = read_json(RESULTS / "metrics_ee.json")["emb_dims"]
    booster = xgb.Booster()
    booster.load_model(str(ARTIFACTS / "model_ee.ubj"))
    scores = booster.get_score(importance_type="gain")
    names = booster.feature_names or [f"f{i}" for i in range(sum(emb_dims.values()))]
    assert len(names) == sum(emb_dims.values()), (len(names), emb_dims)
    block_of = {}
    offset = 0
    for rank in HIER:
        for j in range(emb_dims[rank]):
            block_of[names[offset + j]] = rank
        offset += emb_dims[rank]
    by_rank = {r: 0.0 for r in HIER}
    for feat, gain in scores.items():
        by_rank[block_of[feat]] += gain
    total = sum(by_rank.values())
    return {r: 100.0 * v / total for r, v in by_rank.items()}


def tab(importance: dict[str, dict[str, float]], methods) -> list[str]:
    cols = "l" + "r" * len(methods)
    lines = [f"\\begin{{tabular}}{{{cols}}}", r"\toprule"]
    if len(methods) == 1:
        lines.append(r"Taxonomy rank & Relative importance (\%) \\")
    else:
        lines.append(
            "Taxonomy rank & " + " & ".join(f"{METHOD_TITLE[m]} (\\%)" for m in methods) + r" \\"
        )
    lines.append(r"\midrule")
    for rank in HIER:
        lines.append(
            f"\\texttt{{{rank}}} & "
            + " & ".join(f"{importance[m][rank]:.1f}" for m in methods)
            + r" \\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines


def figure(importance, path):
    fig, ax = plt.subplots(figsize=(5.5, 3.5))
    y = np.arange(len(HIER))
    h = 0.38
    colors = {"EntityEmbeddings": "#4a90d9", "XGBoost": "#aacde8"}
    for k, m in enumerate(METHODS):
        vals = [importance[m][r] for r in HIER]
        ax.barh(
            y + (k - 0.5) * h,
            vals,
            height=h,
            color=colors[m],
            edgecolor="white",
            label=METHOD_TITLE[m],
        )
        for yy, v in zip(y + (k - 0.5) * h, vals):
            ax.text(v + 0.5, yy, f"{v:.1f}%", va="center", fontsize=7)
    ax.set_yticks(y)
    ax.set_yticklabels(HIER)
    ax.invert_yaxis()
    ax.set_xlabel("Relative importance (%, gain)")
    ax.set_xlim(0, max(max(importance[m].values()) for m in METHODS) * 1.2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8, loc="upper right")
    plt.tight_layout()
    plt.savefig(path, dpi=180)
    plt.close(fig)
    print(f"Wrote {path.relative_to(path.parents[2])}")


def main():
    importance = {"EntityEmbeddings": ee_gain_by_rank(), "XGBoost": xgb_gain_by_rank()}
    for m in METHODS:
        print(f"\n{METHOD_TITLE[m]} (gain, % of total)")
        for rank in HIER:
            print(f"  {rank:<8s} {importance[m][rank]:6.1f}")
    write_tex(RESULTS / "tab_feature_importance.tex", tab(importance, ["EntityEmbeddings"]))
    write_tex(RESULTS / "tab_feature_importance_cmp.tex", tab(importance, METHODS))
    write_json(RESULTS / "feature_importance.json", importance)
    figure(importance, RESULTS / "feature_importance.png")


if __name__ == "__main__":
    main()
