"""
Evaluate both shipped models on the held-out test split exactly as users get
them: through taxonbodymassml.predict_mass() (lookup=False), so every number
reported in the manuscript is what the packages return.

Outputs in predictive_models/results/:
  main text (Entity Embeddings only)
    tab_metrics.tex            R2 / RMSE / MAE on the full test set and on mass > 0.1 g
    tab_unk_errors.tex         MAE when the finest known rank is genus .. kingdom
    tab_coverage.tex           empirical coverage of the 90% intervals, stratified vs pooled
    tab_coverage_levels.tex    the same at nominal 80% and 95%
    mass_prediction_ee.png, mass_prediction_ee_gt0.1g.png
  supplement (both models)
    tab_metrics_cmp.tex, tab_unk_errors_cmp.tex, tab_coverage_cmp.tex
    mass_prediction_xgb.png, mass_prediction_xgb_gt0.1g.png
  eval_summary.json            everything above plus conformal quantiles (for make_numbers_tex.py)

Prerequisite: the package cache holds the artifacts being evaluated
(scripts/check_parity.py --sync-cache).

Run from repo root:
  predictive_models/.venv/bin/python scripts/evaluate_models.py
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import taxonbodymassml as tbm  # noqa: E402
from _results_common import (  # noqa: E402
    ARTIFACTS,
    METHOD_FILE,
    METHOD_LABEL,
    METHOD_TITLE,
    METHODS,
    RANKS,
    RESULTS,
    fmt_int,
    load_test,
    mask_to_rank,
    metrics_log10,
    read_json,
    scatter_plot,
    write_json,
    write_tex,
)

FILTER_G = 0.1
ALPHAS = [0.80, 0.90, 0.95]
INTERVAL_METHODS = ["stratified", "pooled"]
CALIB_FILES = {
    "EntityEmbeddings": ("calibration_ee.json", "calibration_by_rank_ee.json"),
    "XGBoost": ("calibration.json", "calibration_by_rank.json"),
}
RANK_LABEL = {
    "genus": r"\texttt{genus} (species unseen; baseline)",
    "family": r"\texttt{family} (genus $=$ UNK)",
    "order": r"\texttt{order}",
    "class": r"\texttt{class}",
    "phylum": r"\texttt{phylum}",
    "kingdom": r"\texttt{kingdom}",
}


def predict(df, method, level=None, interval_method="stratified"):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return tbm.predict_mass(
            df,
            method=method,
            lookup=False,
            include_source=True,
            confidence_interval=level if level is not None else False,
            interval_method=interval_method,
        )


def evaluate_method(method, test):
    y = test["y_log10"].to_numpy()
    mass = test["mass_g"].to_numpy()
    out = predict(test, method)
    pred = np.log10(out["mass_g"].to_numpy())
    res = {"metrics": metrics_log10(y, pred)}
    sel = mass > FILTER_G
    res["metrics_filtered"] = metrics_log10(y[sel], pred[sel])
    res["metrics_filtered"]["pct_of_test"] = 100.0 * sel.mean()
    res["source_rank_counts"] = out["source"].value_counts().to_dict()

    tag = METHOD_FILE[method]
    m, mf = res["metrics"], res["metrics_filtered"]
    scatter_plot(
        mass,
        10**pred,
        m["r2"],
        m["rmse"],
        m["mae"],
        f"$n$ = {m['n']:,}",
        RESULTS / f"mass_prediction_{tag}.png",
    )
    scatter_plot(
        mass[sel],
        10 ** pred[sel],
        mf["r2"],
        mf["rmse"],
        mf["mae"],
        f"$n$ = {mf['n']:,}  (mass $> 10^{{-1}}$ g)",
        RESULTS / f"mass_prediction_{tag}_gt0.1g.png",
    )

    # Masking: finest known rank = genus .. kingdom (genus masks nothing but species)
    masked = {}
    base_mae = None
    for rank in RANKS:
        p = np.log10(predict(mask_to_rank(test, rank), method)["mass_g"].to_numpy())
        mae = float(np.mean(np.abs(y - p)))
        if base_mae is None:
            base_mae = mae
        masked[rank] = {"mae": mae, "delta": mae - base_mae, "factor": 10**mae}
    res["masking"] = masked

    # Coverage of conformal intervals
    coverage = {}
    for rank in RANKS:
        df_r = mask_to_rank(test, rank)
        coverage[rank] = {}
        for im in INTERVAL_METHODS:
            for a in ALPHAS:
                o = predict(df_r, method, level=a, interval_method=im)
                lo, hi = o["lower_bound"].to_numpy(), o["upper_bound"].to_numpy()
                ok = np.isfinite(lo) & np.isfinite(hi)
                cov = float(np.mean((lo[ok] <= mass[ok]) & (mass[ok] <= hi[ok])))
                hw = float(np.mean(np.log10(hi[ok] / lo[ok]) / 2))
                coverage[rank][f"{im}_{int(round(a * 100))}"] = {
                    "coverage": cov,
                    "half_width": hw,
                    "n": int(ok.sum()),
                }
    res["coverage"] = coverage

    # Conformal quantiles straight from the calibration files
    pooled_file, by_rank_file = CALIB_FILES[method]
    pooled = np.asarray(read_json(ARTIFACTS / pooled_file)["residuals"], dtype=float)
    by_rank = read_json(ARTIFACTS / by_rank_file)
    res["calibration"] = {
        "n_calib": int(len(pooled)),
        "q": {f"q{int(round(a * 100))}": float(np.quantile(pooled, a)) for a in ALPHAS},
        "q90_by_rank": {
            r: float(np.quantile(np.asarray(v, dtype=float), 0.90)) for r, v in by_rank.items()
        },
    }
    q90 = res["calibration"]["q"]["q90"]
    res["calibration"]["ten_gram_example"] = {
        "lower_g": 10 ** (1 - q90),
        "upper_g": 10 ** (1 + q90),
        "factor": 10**q90,
    }
    return res


def tab_metrics(summary, methods):
    lines = [
        r"\begin{tabular}{llrrrr}" if len(methods) > 1 else r"\begin{tabular}{lrrrr}",
        r"\toprule",
    ]
    head = ("Model & " if len(methods) > 1 else "") + r"Test set & $R^2$ & RMSE & MAE & $n$ \\"
    lines += [head, r"\midrule"]
    for m in methods:
        pre = f"{METHOD_TITLE[m]} & " if len(methods) > 1 else ""
        full, filt = summary[m]["metrics"], summary[m]["metrics_filtered"]
        lines.append(
            f"{pre}Full test set & {full['r2']:.2f} & {full['rmse']:.2f} & {full['mae']:.2f} & {fmt_int(full['n'])} \\\\"  # noqa: E501
        )
        lines.append(
            f"{pre}Reduced (mass $>0.1$\\,g) & {filt['r2']:.2f} & {filt['rmse']:.2f} & {filt['mae']:.2f} & {fmt_int(filt['n'])} \\\\"  # noqa: E501
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines


def tab_unk(summary, methods):
    if len(methods) == 1:
        m = methods[0]
        lines = [
            r"\begin{tabular}{lrrr}",
            r"\toprule",
            r"Finest known rank & MAE ($\log_{10}$ g) & $\Delta$MAE & median factor \\",
            r"\midrule",
        ]
        for rank in RANKS:
            r = summary[m]["masking"][rank]
            delta = "---" if rank == RANKS[0] else f"${r['delta']:+.3f}$"
            lines.append(
                f"{RANK_LABEL[rank]} & {r['mae']:.3f} & {delta} & {r['factor']:.2f}$\\times$ \\\\"
            )
    else:
        cols = "l" + "rr" * len(methods)
        lines = [
            f"\\begin{{tabular}}{{{cols}}}",
            r"\toprule",
            "Finest known rank & "
            + " & ".join(f"\\multicolumn{{2}}{{c}}{{{METHOD_TITLE[m]}}}" for m in methods)
            + r" \\",
            " & ".join(["", *(["MAE & $\\Delta$MAE"] * len(methods))]) + r" \\",
            r"\midrule",
        ]
        for rank in RANKS:
            cells = []
            for m in methods:
                r = summary[m]["masking"][rank]
                delta = "---" if rank == RANKS[0] else f"${r['delta']:+.3f}$"
                cells.append(f"{r['mae']:.3f} & {delta}")
            lines.append(f"{RANK_LABEL[rank]} & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines


def tab_coverage(summary, methods, alphas):
    """Coverage (%) by finest known rank; one column pair (stratified, pooled) per method x alpha."""  # noqa: E501
    pairs = [(m, a) for m in methods for a in alphas]
    cols = "l" + "r" + "rr" * len(pairs)
    lines = [f"\\begin{{tabular}}{{{cols}}}", r"\toprule"]
    heads = []
    for m, a in pairs:
        label = f"{METHOD_LABEL[m]} " if len(methods) > 1 else ""
        heads.append(f"\\multicolumn{{2}}{{c}}{{{label}nominal {int(round(a * 100))}\\%}}")
    lines.append("Finest known rank & $n$ & " + " & ".join(heads) + r" \\")
    lines.append(" & & " + " & ".join(["stratified & pooled"] * len(pairs)) + r" \\")
    lines.append(r"\midrule")
    for rank in RANKS:
        cells = []
        n = None
        for m, a in pairs:
            key = int(round(a * 100))
            s = summary[m]["coverage"][rank][f"stratified_{key}"]
            p = summary[m]["coverage"][rank][f"pooled_{key}"]
            n = s["n"]
            cells.append(f"{100 * s['coverage']:.1f} & {100 * p['coverage']:.1f}")
        lines.append(f"{RANK_LABEL[rank]} & {fmt_int(n)} & " + " & ".join(cells) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines


def tab_coverage_main(summary, method):
    """Main-text coverage table: stratified half-width and both coverages at 90%."""
    lines = [
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"Finest known rank & $n$ & half-width ($\log_{10}$ g) & \multicolumn{2}{c}{coverage at nominal 90\%} \\",  # noqa: E501
        r"\cmidrule(l){4-5}",
        r" & & stratified & stratified & pooled \\",
        r"\midrule",
    ]
    for rank in RANKS:
        s = summary[method]["coverage"][rank]["stratified_90"]
        p = summary[method]["coverage"][rank]["pooled_90"]
        lines.append(
            f"{RANK_LABEL[rank]} & {fmt_int(s['n'])} & {s['half_width']:.2f} & "
            f"{100 * s['coverage']:.1f}\\% & {100 * p['coverage']:.1f}\\% \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}"]
    return lines


def main():
    test = load_test()
    print(f"Test rows: {len(test):,}")
    summary = {"n_test": int(len(test)), "filter_g": FILTER_G, "alphas": ALPHAS, "methods": {}}
    for method in METHODS:
        print(f"\n== {method} ==")
        summary["methods"][method] = evaluate_method(method, test)
        m = summary["methods"][method]["metrics"]
        print(f"  R2={m['r2']:.4f} RMSE={m['rmse']:.4f} MAE={m['mae']:.4f}")
        for rank in RANKS:
            r = summary["methods"][method]["masking"][rank]
            c = summary["methods"][method]["coverage"][rank]
            print(
                f"  {rank:<8s} MAE={r['mae']:.3f} d={r['delta']:+.3f}  cov90 strat={100 * c['stratified_90']['coverage']:.1f}% pooled={100 * c['pooled_90']['coverage']:.1f}%"  # noqa: E501
            )

    S = summary["methods"]
    write_tex(RESULTS / "tab_metrics.tex", tab_metrics(S, ["EntityEmbeddings"]))
    write_tex(RESULTS / "tab_metrics_cmp.tex", tab_metrics(S, METHODS))
    write_tex(RESULTS / "tab_unk_errors.tex", tab_unk(S, ["EntityEmbeddings"]))
    write_tex(RESULTS / "tab_unk_errors_cmp.tex", tab_unk(S, METHODS))
    write_tex(RESULTS / "tab_coverage.tex", tab_coverage_main(S, "EntityEmbeddings"))
    write_tex(
        RESULTS / "tab_coverage_levels.tex", tab_coverage(S, ["EntityEmbeddings"], [0.80, 0.95])
    )
    write_tex(RESULTS / "tab_coverage_cmp.tex", tab_coverage(S, METHODS, [0.90]))
    write_json(RESULTS / "eval_summary.json", summary)


if __name__ == "__main__":
    main()
