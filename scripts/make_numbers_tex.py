"""
Generate predictive_models/results/numbers.tex: one \\newcommand per number the
manuscript quotes, so the text can never carry a stale value.  The manuscript
\\input{numbers} in development; ms/flatten_manuscript.py substitutes the
literal values for submission.

Inputs (all produced by the other results scripts / the pipeline):
  results/data_stats.json, eval_summary.json, feature_importance.json,
  hyperparams.json, metrics.json, metrics_ee.json, artifacts/checksums.json,
  packages/python/pyproject.toml, packages/r/DESCRIPTION,
  packages/python/taxonbodymassml/_checksums.py, data/Citations_BodyMass.bib,
  installed library versions, `git describe` of ../TaxonBodyMass_DB.

Macro names use letters only (LaTeX), prefixed ee/xgb for per-model values.
Thousands separators are written as {,} so the macros work in text and math.

Run from repo root:
  predictive_models/.venv/bin/python scripts/make_numbers_tex.py [--db-version vX.Y.Z]
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import subprocess
import sys
from importlib import metadata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _results_common import (  # noqa: E402
    ARTIFACTS,
    DATA,
    METHOD_FILE,
    METHODS,
    MODEL_FEATURES,
    RANKS,
    REPO,
    RESULTS,
    fmt_int,
    read_json,
    write_json,
)

RANK_CAP = {r: r.capitalize() for r in RANKS}  # genus -> Genus


def num(x, d=2) -> str:
    return f"{x:.{d}f}"


def signed(x, d=3) -> str:
    return f"{x:+.{d}f}"


def sci(x, sig=2) -> str:
    """1.19e8 -> '1.19 \\times 10^{8}' (math-mode content)."""
    s = f"{x:.{sig - 1}e}"
    mant, exp = s.split("e")
    return f"{mant} \\times 10^{{{int(exp)}}}"


def tex_escape(s: str) -> str:
    return s.replace("_", r"\_").replace("&", r"\&").replace("%", r"\%")


def version_of(pkg: str) -> str:
    try:
        return metadata.version(pkg)
    except metadata.PackageNotFoundError:
        return "unknown"


def first_match(pattern: str, text: str, flags=re.M) -> str:
    m = re.search(pattern, text, flags)
    if not m:
        sys.exit(f"pattern {pattern!r} not found")
    return m.group(1)


def db_version(override: str | None) -> str:
    if override:
        return override
    db = REPO.parent / "TaxonBodyMass_DB"
    try:
        exact = subprocess.run(
            ["git", "-C", str(db), "describe", "--tags", "--exact-match"],
            capture_output=True,
            text=True,
        )
        if exact.returncode == 0:
            return exact.stdout.strip()
        near = subprocess.run(
            ["git", "-C", str(db), "describe", "--tags"], capture_output=True, text=True
        )
        tag = near.stdout.strip()
        print(
            f"  WARNING: TaxonBodyMass_DB HEAD is not tagged ({tag}); tag it or pass --db-version"
        )
        return tag
    except FileNotFoundError:
        return "unknown"


def count_bib_entries(path: Path) -> int:
    import bibtexparser
    from bibtexparser.bparser import BibTexParser

    parser = BibTexParser(common_strings=True)
    parser.ignore_nonstandard_types = False
    with open(path, encoding="utf-8") as f:
        return len(bibtexparser.load(f, parser).entries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-version", default=None)
    args = ap.parse_args()

    data = read_json(RESULTS / "data_stats.json")
    ev = read_json(RESULTS / "eval_summary.json")
    imp = read_json(RESULTS / "feature_importance.json")
    hp = read_json(RESULTS / "hyperparams.json")
    m_xgb = read_json(RESULTS / "metrics.json")
    m_ee = read_json(RESULTS / "metrics_ee.json")
    checksums = read_json(ARTIFACTS / "checksums.json")

    pyproject = (REPO / "packages" / "python" / "pyproject.toml").read_text()
    description = (REPO / "packages" / "r" / "DESCRIPTION").read_text()
    checks_py = (REPO / "packages" / "python" / "taxonbodymassml" / "_checksums.py").read_text()

    M: dict[str, str] = {}

    # ---- data ---------------------------------------------------------------
    M["nDbRecords"] = fmt_int(data["n_db"])
    M["nRecordsUsed"] = fmt_int(data["n_used"])
    M["nDroppedMissingRank"] = fmt_int(data["n_dropped_missing_rank"])
    if data.get("n_source_records"):
        M["nSourceRecords"] = fmt_int(data["n_source_records"])
    M["nSources"] = fmt_int(count_bib_entries(DATA / "Citations_BodyMass.bib"))
    M["nSourceLabels"] = fmt_int(data["n_sources_distinct"])
    M["nLookupSpecies"] = fmt_int(data["n_lookup_species"])
    M["nKingdoms"] = str(len(data["kingdoms"]))
    for k, v in data["kingdoms"].items():
        M[f"n{k}"] = fmt_int(v)
    M["pctAnimalia"] = num(data["pct_animalia"], 1)
    M["nClasses"] = fmt_int(data["n_classes"])
    M["nOrders"] = fmt_int(data["n_orders"])
    M["nFamilies"] = fmt_int(data["n_families"])
    M["nGenera"] = fmt_int(data["n_genera"])
    for letter, (name, n) in zip("ABCDEF", data["top_classes"]):
        M[f"topClass{letter}"] = name
        M[f"nTopClass{letter}"] = fmt_int(n)
    for letter, (name, n) in zip("ABCDEF", data["top_single_source_contributors"]):
        M[f"srcLabel{letter}"] = tex_escape(name)
        M[f"nUniqueSrc{letter}"] = fmt_int(n)
    M["massMinSpecies"] = data["mass_min"]["species"]
    M["massMinG"] = sci(data["mass_min"]["mass_g"], 2)
    M["massMaxSpecies"] = data["mass_max"]["species"]
    M["massMaxG"] = sci(data["mass_max"]["mass_g"], 3)
    M["massMedianG"] = num(data["mass_median_g"], 1)
    M["ordersOfMagnitude"] = num(data["orders_of_magnitude"], 1)
    M["ordersOfMagnitudeInt"] = str(int(round(data["orders_of_magnitude"])))
    chain = data.get("resolution_chain")
    if chain:
        M["nNamesSubmitted"] = fmt_int(chain["n_names_submitted"])
        M["nNamesResolved"] = fmt_int(chain["n_names_resolved"])
        M["nNamesAutotroph"] = fmt_int(chain["n_names_autotroph"])
        M["nSpeciesAfterFilter"] = fmt_int(chain["n_species_after_filter"])

    # ---- split and calibration ---------------------------------------------
    n_train, n_test = int(m_xgb["n_train"]), int(m_xgb["n_test"])
    M["nTrain"] = fmt_int(n_train)
    M["nTest"] = fmt_int(n_test)
    M["pctTest"] = str(int(round(100 * n_test / (n_train + n_test))))
    n_calib = ev["methods"]["EntityEmbeddings"]["calibration"]["n_calib"]
    M["nCalib"] = fmt_int(n_calib)
    M["nCalibFit"] = fmt_int(n_train - n_calib)
    M["splitSeed"] = "42"
    for rank in MODEL_FEATURES:
        M[f"vocab{rank.capitalize()}"] = fmt_int(m_ee["vocab_sizes"][rank] - 1)

    # ---- per-model metrics, intervals, masking, coverage, importance ----------
    for method in METHODS:
        p = METHOD_FILE[method]
        r = ev["methods"][method]
        met, filt = r["metrics"], r["metrics_filtered"]
        M[f"{p}Rsq"] = num(met["r2"], 2)
        M[f"{p}RMSE"] = num(met["rmse"], 2)
        M[f"{p}MAE"] = num(met["mae"], 2)
        M[f"{p}MAEthree"] = num(met["mae"], 3)
        M[f"{p}MAEfactor"] = num(10 ** met["mae"], 2)
        M[f"{p}FilteredN"] = fmt_int(filt["n"])
        M[f"{p}FilteredPct"] = str(int(round(filt["pct_of_test"])))
        M[f"{p}FilteredRsq"] = num(filt["r2"], 2)
        M[f"{p}FilteredRMSE"] = num(filt["rmse"], 2)
        M[f"{p}FilteredMAE"] = num(filt["mae"], 2)
        study = hp[method]
        M[f"{p}CVMAE"] = num(study["best_cv_mae"], 3)
        M[f"{p}NEstimators"] = fmt_int(study["best_params"]["n_estimators"])
        M[f"{p}MaxDepth"] = str(study["best_params"]["max_depth"])
        cal = r["calibration"]
        M[f"{p}Qpooled"] = num(cal["q"]["q90"], 3)
        M[f"{p}QpooledTwo"] = num(cal["q"]["q90"], 2)
        M[f"{p}QpooledFactor"] = num(10 ** cal["q"]["q90"], 1)
        M[f"{p}QeightyPooled"] = num(cal["q"]["q80"], 3)
        M[f"{p}QninetyfivePooled"] = num(cal["q"]["q95"], 3)
        M[f"{p}TenGramLower"] = num(cal["ten_gram_example"]["lower_g"], 1)
        M[f"{p}TenGramUpper"] = num(cal["ten_gram_example"]["upper_g"], 0)
        for rank in RANKS:
            M[f"{p}Q{RANK_CAP[rank]}"] = num(cal["q90_by_rank"][rank], 2)
            mk = r["masking"][rank]
            M[f"{p}MAE{RANK_CAP[rank]}"] = num(mk["mae"], 3)
            M[f"{p}Delta{RANK_CAP[rank]}"] = signed(mk["delta"], 3)
            M[f"{p}Factor{RANK_CAP[rank]}"] = num(mk["factor"], 2)
            cov = r["coverage"][rank]
            M[f"{p}CovStrat{RANK_CAP[rank]}"] = num(100 * cov["stratified_90"]["coverage"], 1)
            M[f"{p}CovPooled{RANK_CAP[rank]}"] = num(100 * cov["pooled_90"]["coverage"], 1)
            M[f"{p}Imp{RANK_CAP[rank]}"] = num(imp[method][rank], 1)
    M["eeStageOneMAE"] = num(m_ee["stage1_mae"], 2)
    M["eeStageOneMAEthree"] = num(m_ee["stage1_mae"], 3)
    M["eeBestTrial"] = str(hp["EntityEmbeddings"].get("best_trial", ""))
    for rank in MODEL_FEATURES:
        M[f"embDim{rank.capitalize()}"] = str(m_ee["emb_dims"][rank])
    M["embDimTotal"] = str(m_ee["total_emb_dim"])
    M["stageOneEpochs"] = str(m_ee["stage1_epochs"])
    M["stageOneBatch"] = str(m_ee["stage1_batch"])
    M["stageOneLR"] = f"{m_ee['stage1_lr']:g}"
    M["nTrials"] = str(hp["XGBoost"]["n_trials"])
    M["nFolds"] = str(hp["XGBoost"]["n_folds"])
    M["tuneSeed"] = "42"

    # ---- versions, tags, sizes ---------------------------------------------
    M["pkgVersionPy"] = first_match(r'^version\s*=\s*"([^"]+)"', pyproject)
    M["pkgVersionR"] = first_match(r"^Version:\s*(\S+)", description)
    art = first_match(r'MODEL_ARTIFACT_VERSION\s*=\s*"([^"]+)"', checks_py)
    M["artifactVersion"] = art
    M["hfTagR"] = f"r-v{art}"
    M["hfTagPy"] = f"py-v{art}"
    M["dbVersion"] = db_version(args.db_version)
    M["xgboostFloorPy"] = first_match(r'"xgboost>=([0-9.]+)"', pyproject)
    M["xgboostFloorR"] = first_match(r"xgboost \(>= ([0-9.]+)\)", description)
    M["xgboostVersion"] = version_of("xgboost")
    M["torchVersion"] = version_of("torch")
    M["optunaVersion"] = version_of("optuna")
    M["sklearnVersion"] = version_of("scikit-learn")
    M["pythonVersion"] = ".".join(map(str, sys.version_info[:2]))
    sizes = {f: (ARTIFACTS / f).stat().st_size for f in checksums if (ARTIFACTS / f).exists()}
    M["nArtifacts"] = str(len(checksums))
    M["artifactsTotalGB"] = num(sum(sizes.values()) / 1e9, 1)
    M["modelUbjMB"] = str(int(round(sizes.get("model.ubj", 0) / 1e6)))
    M["modelEeMB"] = str(int(round(sizes.get("model_ee.ubj", 0) / 1e6)))
    M["embeddingsMB"] = num(sizes.get("embeddings.json", 0) / 1e6, 1)
    M["lookupMB"] = num(sizes.get("lookup.json", 0) / 1e6, 1)
    M["numbersGeneratedDate"] = dt.date.today().isoformat()

    # ---- write --------------------------------------------------------------
    bad = [k for k in M if not re.fullmatch(r"[A-Za-z]+", k)]
    if bad:
        sys.exit(f"macro names must be letters only: {bad}")
    lines = [
        "% numbers.tex -- generated by scripts/make_numbers_tex.py; do not edit by hand.",
        f"% Generated {M['numbersGeneratedDate']} from predictive_models/results/*.json,",
        "% artifacts/checksums.json and the package metadata.  Every macro ends with",
        "% \\xspace so it can be followed by a space or punctuation in running text.",
        "% ms/flatten_manuscript.py replaces the macros by their values for submission.",
    ]
    for k, v in M.items():
        lines.append(f"\\newcommand{{\\{k}}}{{{v}\\xspace}}")
    out = RESULTS / "numbers.tex"
    out.write_text("\n".join(lines) + "\n")
    print(f"Wrote {out.relative_to(REPO)} ({len(M)} macros)")
    write_json(RESULTS / "numbers.json", M)


if __name__ == "__main__":
    main()
