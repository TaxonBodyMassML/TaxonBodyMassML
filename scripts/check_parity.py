"""
Check that every consumer of the XGBoost artifacts reproduces the training
model exactly, using the golden cases written by scripts/export_artifacts.py.

Consumers checked (both methods where the golden file has EE values):
  * Python package (taxonbodymassml, installed in the current interpreter)
  * R package (TaxonBodyMassML, via Rscript on PATH)         -- skipped with --no-r
  * Flask microservice (XGBoost only)                        -- skipped with --no-service

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
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
GOLDEN = REPO_ROOT / "predictive_models" / "results" / "golden_predictions.json"
ARTIFACTS = REPO_ROOT / "artifacts"
TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
TOL = 1e-5  # log10 units; float32 booster output round-tripped through JSON/R


def _report(name, got, expected):
    got = np.asarray(got, dtype=float)
    expected = np.asarray(expected, dtype=float)
    diff = np.abs(got - expected)
    ok = bool(np.all(diff < TOL))
    print(f"  {name:<14s} max|diff| = {diff.max():.2e}  {'OK' if ok else 'MISMATCH'}")
    if not ok:
        for i, d in enumerate(diff):
            if d >= TOL:
                print(f"    case {i}: got {got[i]:.6f} expected {expected[i]:.6f}")
    return ok


def _taxonomy_frame(cases):
    df = pd.DataFrame(cases)[TAXONOMY_COLS]
    return df.rename(columns={"species": "species_resolved"})


def check_python(cases, expected, method):
    import taxonbodymassml as tbm

    df = _taxonomy_frame(cases)
    out = tbm.predict_mass(df, method=method, lookup=False)
    return _report(f"python/{method}", np.log10(out["mass_g"].to_numpy()), expected)


def check_r(cases, expected, method):
    payload = json.dumps(cases)
    script = r"""
    suppressMessages(library(TaxonBodyMassML))
    cases <- jsonlite::fromJSON(file("stdin"), simplifyDataFrame = TRUE)
    df <- cases[, c("kingdom","phylum","class","order","family","genus","species")]
    names(df)[names(df) == "species"] <- "species_resolved"
    out <- predict_mass(df, method = "%s", lookup = FALSE)
    cat(jsonlite::toJSON(log10(out$mass_g), digits = NA))
    """ % method
    res = subprocess.run(["Rscript", "-e", script], input=payload, capture_output=True, text=True)
    if res.returncode != 0:
        print("  R failed:\n" + res.stderr)
        return False
    return _report(f"r/{method}", json.loads(res.stdout.strip().splitlines()[-1]), expected)


def check_service(cases, expected):
    sys.path.insert(0, str(REPO_ROOT / "regressor_microservice"))
    cwd = os.getcwd()
    os.chdir(REPO_ROOT / "regressor_microservice")
    try:
        import regressor

        app = regressor.create_wsgi_app()
    finally:
        os.chdir(cwd)
    client = app.test_client()
    payload = [{c: case[c] for c in TAXONOMY_COLS} for case in cases]
    resp = client.post("/xgb_pred_multi", json=payload)
    assert resp.status_code == 200, resp.get_json()
    # The microservice has no lookup=False switch: species with a recorded mass
    # in the training data come back from the dictionary, everything else from
    # the model.  Compare each row against the appropriate reference.
    lookup = app.config["state"].lookup
    got, ref = [], []
    for case, item, exp in zip(cases, resp.get_json()["items"], expected):
        hit = lookup.get(case["species"])
        got.append(np.log10(item["prediction"]))
        ref.append(np.log10(hit["mass_g"]) if hit else exp)
        if hit:
            assert item["source"] == hit["source"] and item["confidence"] is None, item
    return _report("microservice", got, ref)


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
    expected = [c["log10_mass_g"] for c in cases]
    print(f"{len(cases)} golden cases from {GOLDEN.relative_to(REPO_ROOT)}")

    if args.sync_cache:
        sync_cache()

    methods = {"XGBoost": expected}
    if all("log10_mass_g_ee" in c for c in cases):
        methods["EntityEmbeddings"] = [c["log10_mass_g_ee"] for c in cases]
    results = []
    for method, exp in methods.items():
        results.append(check_python(cases, exp, method))
        if not args.no_r:
            results.append(check_r(cases, exp, method))
    if not args.no_service:
        results.append(check_service(cases, expected))
    if all(results):
        print("PARITY OK")
    else:
        sys.exit("PARITY FAILED")


if __name__ == "__main__":
    main()
