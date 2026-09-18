"""
Hyperparameter and architecture tables for the manuscript supplement.

Reads the tuning studies (best parameters), the training metrics files
(fixed parameters, embedding dimensions, Stage 1 settings) and the search
spaces defined in predictive_models/tune_hyperparameters.py (parsed with ast so
nothing is executed), and writes

  predictive_models/results/tab_hyperparams_ee.tex     Entity Embeddings Stage 2 XGBoost
  predictive_models/results/tab_hyperparams_xgb.tex    direct XGBoost
  predictive_models/results/tab_ee_architecture.tex    Stage 1 embedding MLP
  predictive_models/results/hyperparams.json  values; tuned params at a search bound

Run from repo root:
  predictive_models/.venv/bin/python scripts/extract_hyperparameters.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _results_common import (  # noqa: E402
    MODEL_FEATURES,
    REPO,
    RESULTS,
    fmt_int,
    read_json,
    write_json,
    write_tex,
)

TUNER = REPO / "predictive_models" / "tune_hyperparameters.py"

DESCRIPTION = {
    "objective": r"MAE loss, $\log_{10}$ space",
    "enable_categorical": "Native categorical splits",
    "random_state": "Reproducibility seed",
    "n_estimators": "Trees in ensemble",
    "max_depth": "Maximum tree depth",
    "learning_rate": "Step size per tree",
    "subsample": "Row sampling fraction per tree",
    "colsample_bytree": "Feature sampling fraction per tree",
    "gamma": "Min.\\ loss reduction to split a node",
    "min_child_weight": "Minimum sum of instance weight in a leaf",
    "reg_alpha": "L1 regularisation on leaf weights",
    "reg_lambda": "L2 regularisation on leaf weights",
}
DEFAULTS = {"reg_alpha": "0", "reg_lambda": "1"}
TUNED_ORDER = [
    "n_estimators",
    "max_depth",
    "learning_rate",
    "subsample",
    "colsample_bytree",
    "gamma",
    "min_child_weight",
]


def load_search_spaces() -> dict:
    """Return {'XGB_SPACE': ..., 'EE_SPACE': ..., 'XGB_FIXED': ..., 'EE_FIXED': ...} from the tuner source."""  # noqa: E501
    tree = ast.parse(TUNER.read_text())
    out = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", None)
            if name in {"XGB_SPACE", "EE_SPACE", "XGB_FIXED", "EE_FIXED"}:
                out[name] = ast.literal_eval(node.value)
    missing = {"XGB_SPACE", "EE_SPACE", "XGB_FIXED", "EE_FIXED"} - set(out)
    if missing:
        sys.exit(f"{TUNER} lacks {sorted(missing)}")
    return out


def fmt_value(v) -> str:
    if isinstance(v, bool):
        return r"\texttt{True}" if v else r"\texttt{False}"
    if isinstance(v, int):
        return fmt_int(v)
    if isinstance(v, float):
        return f"{v:.4g}" if v < 1 else f"{v:.4g}"
    return f"\\texttt{{{v}}}"


def fmt_range(spec) -> str:
    kind, lo, hi = spec[0], spec[1], spec[2]
    if kind == "int":
        step = f" (step {spec[3]})" if len(spec) > 3 and spec[3] != 1 else ""
        return f"{fmt_int(lo)}--{fmt_int(hi)}{step}"
    if kind == "float_log":
        return f"{lo:g}--{hi:g} (log)"
    return f"{lo:g}--{hi:g}"


def at_bound(value, spec) -> str | None:
    lo, hi = spec[1], spec[2]
    if value == lo:
        return "lower"
    if value == hi:
        return "upper"
    return None


def hyperparam_table(best: dict, fixed: dict, space: dict, seed: int) -> tuple[list[str], dict]:
    # Four columns: the "Search range" cell reads "fixed" / "default" for
    # untuned parameters; a tuned value at an edge of its range gets an asterisk.
    lines = [
        r"\begin{tabular}{lrlp{5.2cm}}",
        r"\toprule",
        r"Parameter & Value & Search range & Description \\",
        r"\midrule",
    ]
    # Backslashes are not allowed inside f-string expressions before Python 3.12,
    # so the TeX-escaped parameter name is built outside the f-strings.
    for name, val in fixed.items():
        v = seed if val == "SEED" else val
        tex = name.replace("_", r"\_")
        lines.append(
            f"\\texttt{{{tex}}} & {fmt_value(v)} & fixed & {DESCRIPTION.get(name, '')} \\\\"
        )
    bounds = {}
    for name in TUNED_ORDER:
        if name not in best:
            continue
        b = at_bound(best[name], space[name])
        bounds[name] = b
        note = "$^{*}$" if b else ""
        tex = name.replace("_", r"\_")
        lines.append(
            f"\\texttt{{{tex}}} & {fmt_value(best[name])} & "
            f"{fmt_range(space[name])}{note} & {DESCRIPTION.get(name, '')} \\\\"
        )
    for name, v in DEFAULTS.items():
        tex = name.replace("_", r"\_")
        lines.append(f"\\texttt{{{tex}}} & {v} & default & {DESCRIPTION[name]} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines, bounds


def architecture_table(mee: dict, stage1_mae: float) -> list[str]:
    dims = mee["emb_dims"]
    vocab = mee["vocab_sizes"]
    total = mee["total_emb_dim"]
    lines = [
        r"\begin{tabular}{lrr}",
        r"\toprule",
        r"Rank & Training vocabulary (excl.\ UNK) & Embedding dimensions \\",
        r"\midrule",
    ]
    for rank in MODEL_FEATURES:
        lines.append(f"\\texttt{{{rank}}} & {fmt_int(vocab[rank] - 1)} & {dims[rank]} \\\\")
    lines.append(f"Concatenated input & & {total} \\\\")
    lines += [
        r"\midrule",
        r"\multicolumn{3}{l}{\textit{Stage 1 network and training}} \\",
        f"Hidden layers & \\multicolumn{{2}}{{r}}{{{total} $\\rightarrow$ 64 $\\rightarrow$ 32 $\\rightarrow$ 1, ReLU}} \\\\",  # noqa: E501
        r"Loss & \multicolumn{2}{r}{L1 (MAE in $\log_{10}$ g)} \\",
        f"Optimiser & \\multicolumn{{2}}{{r}}{{Adam, learning rate {mee['stage1_lr']:g}, OneCycleLR schedule}} \\\\",  # noqa: E501
        f"Epochs / batch size & \\multicolumn{{2}}{{r}}{{{mee['stage1_epochs']} / {mee['stage1_batch']}}} \\\\",  # noqa: E501
        r"Seeds & \multicolumn{2}{r}{PyTorch and NumPy 42} \\",
        r"UNK vector & \multicolumn{2}{r}{mean of the rank's learned embeddings} \\",
        f"Stage 1 test MAE & \\multicolumn{{2}}{{r}}{{{stage1_mae:.3f} $\\log_{{10}}$ g}} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
    ]
    return lines


def main():
    spaces = load_search_spaces()
    xgb_study = read_json(RESULTS / "tuning_study.json")
    ee_study = read_json(RESULTS / "tuning_study_ee.json")
    m_xgb = read_json(RESULTS / "metrics.json")
    m_ee = read_json(RESULTS / "metrics_ee.json")
    seed = int(m_xgb["hyperparameters"].get("random_state", 42))

    xgb_lines, xgb_bounds = hyperparam_table(
        xgb_study["best_params"], spaces["XGB_FIXED"], spaces["XGB_SPACE"], seed
    )
    ee_lines, ee_bounds = hyperparam_table(
        ee_study["best_params"], spaces["EE_FIXED"], spaces["EE_SPACE"], seed
    )
    write_tex(RESULTS / "tab_hyperparams_xgb.tex", xgb_lines)
    write_tex(RESULTS / "tab_hyperparams_ee.tex", ee_lines)
    write_tex(RESULTS / "tab_ee_architecture.tex", architecture_table(m_ee, m_ee["stage1_mae"]))

    summary = {
        "XGBoost": {
            "best_params": xgb_study["best_params"],
            "best_cv_mae": xgb_study["best_cv_mae"],
            "n_trials": xgb_study["n_trials"],
            "n_folds": xgb_study["n_folds"],
            "at_bound": {k: v for k, v in xgb_bounds.items() if v},
            "search_space": spaces["XGB_SPACE"],
        },
        "EntityEmbeddings": {
            "best_params": ee_study["best_params"],
            "best_cv_mae": ee_study["best_cv_mae"],
            "n_trials": ee_study["n_trials"],
            "n_folds": ee_study["n_folds"],
            "at_bound": {k: v for k, v in ee_bounds.items() if v},
            "search_space": spaces["EE_SPACE"],
            "emb_dims": m_ee["emb_dims"],
            "total_emb_dim": m_ee["total_emb_dim"],
            "stage1": {
                "epochs": m_ee["stage1_epochs"],
                "batch": m_ee["stage1_batch"],
                "lr": m_ee["stage1_lr"],
                "mae": m_ee["stage1_mae"],
            },
        },
    }
    write_json(RESULTS / "hyperparams.json", summary)
    for m, s in summary.items():
        print(
            f"{m}: best CV MAE {s['best_cv_mae']:.4f}; at search bound: {s['at_bound'] or 'none'}"
        )


if __name__ == "__main__":
    main()
