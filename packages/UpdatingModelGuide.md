# Updating the Model Packages

Follow these steps after retraining or otherwise updating the XGBoost model.
The two packages — `python/` and `r/` — both embed SHA-256 checksums for the
model artifacts. Those checksums must be kept in sync with whatever is live on
Hugging Face, or the packages will refuse to load.

> **Publishing requires explicit approval.** Nothing below uploads or tags
> anything until `python scripts/publish_artifacts.py --yes` is run by hand.

## The encoding contract (read this first)

Everything that touches taxonomy features imports
`predictive_models/taxonomy_encoding.py`:

* The models are trained on `MODEL_FEATURES` = kingdom, phylum, class, order,
  family, genus, as **native categorical** columns (`enable_categorical=True`).
  **Species is not a feature.** The training table has one row per species, so
  a species feature can only memorise individual rows; every species the model
  is asked about is unseen by construction (known species are answered from
  the `lookup.json` dictionary), so the feature carries no information at
  inference and only absorbs signal that belongs to the hierarchy. Dropping it
  improved both models. `TAXONOMY_COLS` (kingdom .. species) remains the full
  taxonomy used for lookup, genus promotion and source-rank inference.
* Each column's vocabulary is `["UNK"] + sorted(unique training values)` and is
  built from `train.csv` only. `categories.json` *is* that vocabulary, so the
  list index equals the training integer code. The order is alphabetical with
  UNK first **because** that is the training order — never reorder it.
* Inference code (Python package, R package, microservice, scripts) builds
  `pd.Categorical` / `factor` columns whose categories are exactly
  `categories.json`, and orders columns by the **model's own** `feature_names`.
  There is no `feature_order` key; xgboost does not reorder by name, so
  reading the order from anywhere else would silently mispredict.

---

## Step 1 — Retrain the model

Run the training script from the repository root:

```bash
python predictive_models/decision_tree.py
```

This fits the model twice (once on 80 % of the training split for conformal
calibration, once on all of it) and writes the bundle — model, `q`, `vocab`,
pooled and per-rank calibration residuals, and the species dictionary — to:

```
regressor_microservice/sliced_model/xgboost_model.pkl.*
```

Stale `.pkl.N` slices from earlier runs are deleted first. Commit the new
slices and `git rm` any that no longer exist.

---

## Step 2 — Export the artifacts

Run the export script from the repository root:

```bash
python scripts/export_artifacts.py
```

This reads the bundle from Step 1, checks the contract (feature names equal
`TAXONOMY_COLS`, all feature types categorical, vocabulary UNK-first and
sorted), and regenerates these files in `artifacts/`:

| File | Description |
|---|---|
| `model.ubj` | XGBoost model in binary UBJSON format |
| `calibration.json` | Sorted pooled conformal residuals |
| `calibration_by_rank.json` | Rank-stratified conformal residuals |
| `categories.json` | Training vocabulary per model feature, kingdom .. genus (UNK first, then sorted; index == code) |
| `lookup.json` | Species → `{mass_g, source}` dictionary from training data (also carried in the pickle bundle for the microservice) |
| `checksums.json` | SHA-256 hashes of the above plus the Entity Embeddings files — the source of truth |

It also writes `predictive_models/results/golden_predictions.json`: reference
log10 predictions for a fixed set of inputs (test rows, each rank-level UNK
masking, all-UNK, unseen taxa). Every consumer must reproduce them. Because
species is not a feature, a test row and the same row with species masked
give the same value by design.

### Step 2b — Check parity before touching checksums

```bash
predictive_models/.venv/bin/python scripts/check_parity.py --sync-cache --no-service
regressor_microservice/.venv/bin/python scripts/check_parity.py --no-r
```

`--sync-cache` copies `artifacts/` into the Python and R package cache
directories so the packages can be tested against the new model before it is
published. The check fails if the Python package, the R package or the
microservice differ from the golden values by more than 1e-5 log10 units.

---

## Step 3 — Upload to Hugging Face

**Only with explicit approval.** Bump the version in `packages/r/DESCRIPTION`
and `packages/python/pyproject.toml` first — the script refuses to publish if
the `r-v<version>` / `py-v<version>` tags already exist, because re-using a
tag would leave it pointing at the old artifacts. Then:

```bash
pip install huggingface_hub
hf auth login
python scripts/publish_artifacts.py          # dry run: prints what it would do
python scripts/publish_artifacts.py --yes    # upload, delete stale files, tag
```

The script also deletes retired artifacts (currently `*gpboost*`) from the
Hub and rewrites `MODEL_ARTIFACT_VERSION` in both packages.

---

## Step 4 — Update the Python package checksums

Open `python/taxonbodymassml/_checksums.py` and replace the SHA-256 values
with the ones from `artifacts/checksums.json` (all XGBoost files, plus the
Entity Embeddings files if they changed):

```python
CHECKSUMS = {
    "model.ubj":                "<new sha256 from checksums.json>",
    "calibration.json":         "<new sha256 from checksums.json>",
    "calibration_by_rank.json": "<new sha256 from checksums.json>",
    "categories.json":          "<new sha256 from checksums.json>",
    "lookup.json":              "<new sha256 from checksums.json>",
    ...
}
```

Until the artifacts are published, the CI step that downloads
`categories.json` from Hugging Face and compares it to this checksum will
fail — that is expected and is the signal that the publish step is pending.

Do not edit the `HF_REPO_ID` line unless the Hugging Face repository has moved.
The file header says "do not edit by hand" — this is a reminder that the values
come from `export_artifacts.py`, not that the file is literally off-limits.

---

## Step 5 — Update the R package checksums

Open `r/R/model.R` and replace the SHA-256 values in the `.CHECKSUMS` list
with the same values from `artifacts/checksums.json`:

```r
.CHECKSUMS <- list(
  "model.ubj"                = "<new sha256 from checksums.json>",
  "calibration.json"         = "<new sha256 from checksums.json>",
  "calibration_by_rank.json" = "<new sha256 from checksums.json>",
  "categories.json"          = "<new sha256 from checksums.json>",
  "lookup.json"              = "<new sha256 from checksums.json>",
  ...
)
```

---

## Step 6 — Release both packages

**Only with explicit approval.** Tag and release the updated Python and R
packages so downstream users receive the new integrity constants. Both packages download the artifacts from Hugging
Face on first use and verify them against these checksums, so users with a
cached copy of the old model will re-download automatically when they upgrade
the package.

---

## Updating the Entity Embeddings Model

The Entity Embeddings model writes its artifacts directly to `artifacts/`
when the training script is run. It is not yet processed by `export_artifacts.py`
and is not currently referenced by the Python or R packages.

### Hyperparameter tuning (optional, before retraining)

Before retraining, check whether updated hyperparameters improve cross-validation MAE:

```bash
python predictive_models/tune_hyperparameters.py --model ee
```

The tuner and the training scripts share `predictive_models/taxonomy_encoding.py`,
so the encoding used during tuning is the one used for training.

Review the output JSON in `predictive_models/results/` and, if `best_cv_mae` beats the
current test MAE in `metrics_ee.json`, apply the best params
to the model file before running the training script. See
`predictive_models/TUNING_PLAN.md` (Section 5) for details.

### Entity Embeddings

Run the training script from the repository root:

```bash
python predictive_models/entity_embeddings_model.py
```

Artifacts written to `artifacts/`:

| File | Description |
|---|---|
| `embeddings.json` | Per-column embedding lookup tables `{col: {value: [floats]}}` |
| `model_ee.ubj` | Stage 2 XGBoost in binary UBJSON format |
| `calibration_ee.json` | Pooled conformal prediction residuals |
| `calibration_by_rank_ee.json` | Rank-stratified conformal residuals (genus → kingdom) |

Metrics written to `predictive_models/results/metrics_ee.json`.

### Uploading to Hugging Face and updating checksums

`export_artifacts.py` currently handles only the primary XGBoost artifacts. Upload
EE artifacts to Hugging Face and update package checksums only when the
Python and R packages add explicit support for these models.
