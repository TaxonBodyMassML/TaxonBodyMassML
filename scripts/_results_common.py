"""
Shared helpers for the manuscript results scripts (scripts/extract_*.py,
scripts/evaluate_models.py, scripts/make_numbers_tex.py).

Not a CLI.  Import with ``sys.path.insert(0, str(Path(__file__).parent))``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data"
ARTIFACTS = REPO / "artifacts"
RESULTS = REPO / "predictive_models" / "results"
RESULTS.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(REPO / "predictive_models"))
from taxonomy_encoding import MODEL_FEATURES, RANKS_FINER, TAXONOMY_COLS, UNK  # noqa: E402,F401

METHODS = ["EntityEmbeddings", "XGBoost"]
METHOD_LABEL = {"EntityEmbeddings": "EE", "XGBoost": "XGB"}
METHOD_TITLE = {"EntityEmbeddings": "Entity Embeddings", "XGBoost": "XGBoost"}
METHOD_FILE = {"EntityEmbeddings": "ee", "XGBoost": "xgb"}
RANKS = list(RANKS_FINER)  # genus, family, order, class, phylum, kingdom


def load_test() -> pd.DataFrame:
    """Test split with the columns predict_mass() expects plus y_log10."""
    test = pd.read_csv(DATA / "split" / "test.csv")
    df = test.rename(columns={"species": "species_resolved"})
    df["y_log10"] = np.log10(df["mass_g"].to_numpy())
    return df


def mask_to_rank(df: pd.DataFrame, rank: str) -> pd.DataFrame:
    """Copy of df with every rank finer than `rank` (and the species) set to UNK.

    Mirrors the calibration masking in the training scripts: the finest known
    rank of the query becomes `rank`.
    """
    out = df.copy()
    for col in RANKS_FINER[rank]:
        out[col] = UNK
    out["species_resolved"] = UNK
    return out


def metrics_log10(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    resid = y_true - y_pred
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y_true - y_true.mean()) ** 2))
    return {
        "r2": 1.0 - ss_res / ss_tot,
        "rmse": float(np.sqrt(np.mean(resid**2))),
        "mae": float(np.mean(np.abs(resid))),
        "n": int(len(y_true)),
    }


def read_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def write_json(path: Path, obj) -> None:
    with open(path, "w") as f:
        json.dump(obj, f, indent=2)
    print(f"Wrote {path.relative_to(REPO)}")


def write_tex(path: Path, lines: list[str]) -> None:
    path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {path.relative_to(REPO)}")


def fmt_int(n) -> str:
    """Thousands separator that renders correctly in both text and math mode."""
    return f"{int(n):,}".replace(",", "{,}")


def scatter_plot(y_true_g, y_hat_g, r2_v, rmse_v, mae_v, n_label, path):
    """Predicted vs actual body mass (grams, log axes); metrics annotated in log10 space."""
    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.scatter(y_true_g, y_hat_g, s=4.5, alpha=0.35, color="#0b0b0b", linewidths=0, rasterized=True)
    lims = [min(y_true_g.min(), y_hat_g.min()), max(y_true_g.max(), y_hat_g.max())]
    ax.plot(lims, lims, lw=1, color="#52514e", zorder=5)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("Actual body mass (g)", fontsize=9)
    ax.set_ylabel("Predicted body mass (g)", fontsize=9)
    ax.tick_params(labelsize=8, labelcolor="#0b0b0b", color="#c3c2b7", which="both")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#c3c2b7")
    ax.spines["bottom"].set_color("#c3c2b7")
    ax.text(
        0.04,
        0.96,
        f"$R^2$ = {r2_v:.3f}\nRMSE = {rmse_v:.3f}\nMAE = {mae_v:.3f}"
        f"  ($\\log_{{10}}$ space)\n{n_label}",
        transform=ax.transAxes,
        fontsize=8,
        va="top",
        color="#52514e",
    )
    fig.tight_layout()
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Wrote {Path(path).relative_to(REPO)}")
