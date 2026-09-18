"""
Check that every consumer of the model artifacts reproduces the training
models exactly, using the golden cases written by scripts/export_artifacts.py.

Consumers checked (both methods where the golden file has EE values):
  * Python package (taxonbodymassml, installed in the current interpreter)
  * R package (TaxonBodyMassML, via Rscript on PATH)         -- skipped with --no-r
  * Flask microservice (serves the method in its TBM_METHOD)  -- skipped with --no-service

Golden cases flagged ``expect_na`` have no model feature in the training
vocabulary; consumers must return NA/null for them rather than the all-UNK
extrapolation, and the numeric comparison is skipped for those rows.

The packages read artifacts from their user cache directories, so copy
artifacts/ there first (see packages/UpdatingModelGuide.md) or run with
--sync-cache to do it for you.  The microservice needs Flask, so run this
from an interpreter that has it (e.g. regressor_microservice/.venv) or pass
--no-service.

Run from the repository root:
    predictive_models/.venv/bin/python scripts/check_parity.py --sync-cache --no-service
    regressor_microservice/.venv/bin/python scripts/check_parity.py --no-r
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = REPO_ROOT / "predictive_models" / "results" / "golden_predictions.json"
ARTIFACTS = REPO_ROOT / "artifacts"
TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
TOL = 1e-5  # log10 units; float32 booster output round-tripped through JSON/R


def _to_float(values):
    """JSON null / None / NA -> nan; everything else -> float."""
    return np.array([np.nan if v is None else float(v) for v in values], dtype=float)


def _report(name, got, expected, expect_na):
    got = _to_float(got)
    expected = _to_float(expected)
    expect_na = np.asarray(expect_na, dtype=bool)
    ok = True
    if expect_na.any():
        na_ok = bool(np.all(np.isnan(got[expect_na])))
        ok &= na_ok
        if not na_ok:
            for i in np.flatnonzero(expect_na & ~np.isnan(got)):
                print(f"    case {i}: expected NA, got {got[i]:.6f}")
    num = ~expect_na
    diff = np.abs(got[num] - expected[num])
    num_ok = bool(np.all(np.isfinite(diff)) and np.all(diff < TOL))
    ok &= num_ok
    max_diff = np.nanmax(diff) if diff.size else 0.0
    print(f"  {name:<14s} max|diff| = {max_diff:.2e}  {'OK' if ok else 'MISMATCH'}")
    if not num_ok:
        for j, i in enumerate(np.flatnonzero(num)):
            if not (diff[j] < TOL):
                print(f"    case {i}: got {got[i]:.6f} expected {expected[i]:.6f}")
    return ok


def _taxonomy_frame(cases):
    df = pd.DataFrame(cases)[TAXONOMY_COLS]
    return df.rename(columns={"species": "species_resolved"})


def _expect_na(cases):
    return [bool(c.get("expect_na", False)) for c in cases]


def check_python(cases, expected, method):
    import taxonbodymassml as tbm

    df = _taxonomy_frame(cases)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # expect_na cases warn by design
        out = tbm.predict_mass(df, method=method, lookup=False)
    return _report(
        f"python/{method}", np.log10(out["mass_g"].to_numpy()), expected, _expect_na(cases)
    )


def check_r(cases, expected, method):
    payload = json.dumps(cases)
    script = r"""
    suppressMessages(library(TaxonBodyMassML))
    cases <- jsonlite::fromJSON(file("stdin"), simplifyDataFrame = TRUE)
    df <- cases[, c("kingdom","phylum","class","order","family","genus","species")]
    names(df)[names(df) == "species"] <- "species_resolved"
    out <- suppressWarnings(predict_mass(df, method = "%s", lookup = FALSE))
    cat(jsonlite::toJSON(log10(out$mass_g), digits = NA, na = "null"))
    """ % method
    res = subprocess.run(["Rscript", "-e", script], input=payload, capture_output=True, text=True)
    if res.returncode != 0:
        print("  R failed:\n" + res.stderr)
        return False
    got = json.loads(res.stdout.strip().splitlines()[-1])
    return _report(f"r/{method}", got, expected, _expect_na(cases))


def check_service(cases, by_method):
    sys.path.insert(0, str(REPO_ROOT / "regressor_microservice"))
    cwd = os.getcwd()
    os.chdir(REPO_ROOT / "regressor_microservice")
    try:
        import regressor

        app = regressor.create_wsgi_app()
    finally:
        os.chdir(cwd)
    client = app.test_client()
    state = app.config["state"]
    method = getattr(state, "method", "XGBoost")
    expected = by_method.get(method)
    if expected is None:
        print(f"  microservice serves {method} but the golden file has no values for it")
        return False
    payload = [{c: case[c] for c in TAXONOMY_COLS} for case in cases]
    resp = client.post("/xgb_pred_multi", json=payload)
    assert resp.status_code == 200, resp.get_json()
    # The microservice has no lookup=False switch: species with a recorded mass
    # in the training data come back from the dictionary, everything else from
    # the model.  Compare each row against the appropriate reference.
    lookup = state.lookup
    got, ref = [], []
    for case, item, exp in zip(cases, resp.get_json()["items"], expected):
        hit = lookup.get(case["species"])
        pred = item["prediction"]
        got.append(None if pred is None else np.log10(pred))
        ref.append(np.log10(hit["mass_g"]) if hit else exp)
        if hit:
            assert item["source"] == hit["source"] and item["confidence"] is None, item
    expect_na = [bool(c.get("expect_na", False)) and c["species"] not in lookup for c in cases]
    return _report(f"service/{method}", got, ref, expect_na)


def sync_cache():
    from platformdirs import user_cache_dir

    targets = [Path(user_cache_dir("TaxonBodyMassML"))]
    r_dir = subprocess.run(
        ["Rscript", "-e", 'cat(tools::R_user_dir("TaxonBodyMassML", "cache"))'],
        capture_output=True,
        text=True,
    )
    if r_dir.returncode == 0 and r_dir.stdout.strip():
        targets.append(Path(r_dir.stdout.strip()))
    for target in targets:
        target.mkdir(parents=True, exist_ok=True)
        for f in ARTIFACTS.glob("*"):
            if f.is_file() and f.name != "checksums.json":
                shutil.copy2(f, target / f.name)
        print(f"  synced artifacts → {target}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-r", action="store_true")
    parser.add_argument("--no-service", action="store_true")
    parser.add_argument(
        "--sync-cache", action="store_true", help="copy artifacts/ into package caches"
    )
    args = parser.parse_args()

    golden = json.loads(GOLDEN.read_text())
    cases = golden["cases"]
    n_na = sum(_expect_na(cases))
    print(f"{len(cases)} golden cases from {GOLDEN.relative_to(REPO_ROOT)} ({n_na} expect NA)")

    if args.sync_cache:
        sync_cache()

    by_method = {"XGBoost": [c["log10_mass_g"] for c in cases]}
    if all("log10_mass_g_ee" in c for c in cases):
        by_method["EntityEmbeddings"] = [c["log10_mass_g_ee"] for c in cases]
    results = []
    for method, exp in by_method.items():
        results.append(check_python(cases, exp, method))
        if not args.no_r:
            results.append(check_r(cases, exp, method))
    if not args.no_service:
        results.append(check_service(cases, by_method))
    if all(results):
        print("PARITY OK")
    else:
        sys.exit("PARITY FAILED")


if __name__ == "__main__":
    main()
