DB_CSV    = ../TaxonBodyMass_DB/TaxonBodyMass.csv
LOCAL_CSV = data/TaxonBodyMass.csv
SPLIT     = data/split/train.csv
TUNE_XGB  = predictive_models/results/tuning_study.json
TUNE_EE   = predictive_models/results/tuning_study_ee.json

.PHONY: all fetch split \
        tune tune-xgboost tune-ee \
        train train-xgboost train-ee \
        artifacts publish clean-tune \
        results check-ms submission

all: artifacts

# ---- Fetch updated source data -----------------------------------------------
$(LOCAL_CSV): $(DB_CSV)
	python scripts/fetch_source_data.py

# ---- Train/test split ---------------------------------------------------------
$(SPLIT): $(LOCAL_CSV)
	python data_partition/data_split_visualization.py

split: $(SPLIT)

# ---- Hyperparameter tuning (independent; use -j2 to run in parallel) ---------
$(TUNE_XGB): $(SPLIT)
	python predictive_models/tune_hyperparameters.py --model xgboost

$(TUNE_EE): $(SPLIT)
	python predictive_models/tune_hyperparameters.py --model ee

tune-xgboost: $(TUNE_XGB)
tune-ee: $(TUNE_EE)
tune: tune-xgboost tune-ee

# ---- Training (each reads best params from its tuning JSON at runtime) --------
train-xgboost: $(TUNE_XGB)
	python predictive_models/decision_tree.py

train-ee: $(TUNE_EE)
	python predictive_models/entity_embeddings_model.py

train: train-xgboost train-ee

# ---- Artifact export ----------------------------------------------------------
artifacts: train
	python scripts/export_artifacts.py

# ---- Publish to HuggingFace (upload + versioned tag) -------------------------
publish: artifacts
	python scripts/publish_artifacts.py

# ---- Manuscript results (after `make artifacts` and check_parity.py --sync-cache) ----
# Tables, figures and numbers.tex from the artifacts in the package cache, then
# copied into ms/.  Every number the manuscript quotes comes from numbers.tex.
results:
	python scripts/extract_training_stats.py
	python scripts/evaluate_models.py
	python scripts/extract_feature_importance.py
	python scripts/extract_hyperparameters.py
	python scripts/format_data_sources.py
	python scripts/make_numbers_tex.py
	bash ms/copy_results.sh

# Cross-check ms/manuscript.tex against numbers.tex (unused/undefined macros, margin notes)
check-ms:
	python scripts/check_manuscript_numbers.py

# Single-file, macro-free submission copy (ms/submission/), verified by a pdftotext diff
submission:
	$(MAKE) -C ms submission

# ---- Discard stale tuning state (re-run after data changes) ------------------
clean-tune:
	rm -f predictive_models/results/tuning.db \
	      predictive_models/results/tuning_study.json \
	      predictive_models/results/tuning_ee.db \
	      predictive_models/results/tuning_study_ee.json
