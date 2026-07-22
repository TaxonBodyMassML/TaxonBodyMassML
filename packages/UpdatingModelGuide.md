# Updating the Model Packages

Follow these steps after retraining or otherwise updating the XGBoost model.
The two packages — `python/` and `r/` — both embed SHA-256 checksums for the
model artifacts. Those checksums must be kept in sync with whatever is live on
Hugging Face, or the packages will refuse to load.

---

## Step 1 — Retrain the model

Run the training script from the repository root:

```bash
python predictive_models/decision_tree.py
```

This writes the updated model bundle to:

```
regressor_microservice/sliced_model/xgboost_model.pkl
```

---

## Step 2 — Export the artifacts

Run the export script from the repository root:

```bash
python scripts/export_artifacts.py
```

This reads the bundle from Step 1 and regenerates four files in `artifacts/`:

| File | Description |
|---|---|
| `model.ubj` | XGBoost model in binary UBJSON format (~2 GB) |
| `calibration.json` | Sorted conformal prediction residuals |
| `categories.json` | Taxonomy category lists in training-time code order |
| `checksums.json` | SHA-256 hashes of the above three — the source of truth |

The script prints a sanity check comparing the rebuilt calibration quantile
against the value stored in the bundle. If they differ by more than 1e-4 it
will raise an error — do not proceed until that is resolved.

> **Note on `categories.json` ordering:** The categories must be listed in
> training-time integer-code order (the order the model assigned them during
> training), *not* alphabetical order. `export_artifacts.py` extracts them
> directly from the model's internal `cats.enc` structure to guarantee this.
> Using alphabetical order causes wrong predictions in R because
> `xgb.DMatrix` uses 0-based factor codes that must align with the model's
> internal encoding.

---

## Step 3 — Upload to Hugging Face

Install the CLI if needed, then upload all four artifact files:

```bash
pip install huggingface_hub
huggingface-cli login
huggingface-cli upload marknovak/TaxonBodyMassML artifacts/ . --repo-type model
```

---

## Step 4 — Update the Python package checksums

Open `python/taxonbodymassml/_checksums.py` and replace the three SHA-256
values with the ones from `artifacts/checksums.json`:

```python
CHECKSUMS = {
    "model.ubj":        "<new sha256 from checksums.json>",
    "calibration.json": "<new sha256 from checksums.json>",
    "categories.json":  "<new sha256 from checksums.json>",
}
```

Do not edit the `HF_REPO_ID` line unless the Hugging Face repository has moved.
The file header says "do not edit by hand" — this is a reminder that the values
come from `export_artifacts.py`, not that the file is literally off-limits.

---

## Step 5 — Update the R package checksums

Open `r/R/model.R` and replace the three SHA-256 values in the `.CHECKSUMS`
list (lines 16–20) with the same values from `artifacts/checksums.json`:

```r
.CHECKSUMS <- list(
  "model.ubj"        = "<new sha256 from checksums.json>",
  "calibration.json" = "<new sha256 from checksums.json>",
  "categories.json"  = "<new sha256 from checksums.json>"
)
```

> **Note:** The closing message printed by `export_artifacts.py` incorrectly
> refers to `R/checksums.R`. That file does not exist. The checksums live in
> `R/model.R`.

---

## Step 6 — Release both packages

Tag and release the updated Python and R packages so downstream users receive
the new integrity constants. Both packages download the artifacts from Hugging
Face on first use and verify them against these checksums, so users with a
cached copy of the old model will re-download automatically when they upgrade
the package.
