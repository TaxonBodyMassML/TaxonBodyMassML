DB_CSV    = ../TaxonBodyMass_DB/TaxonBodyMass.csv
LOCAL_CSV = data/TaxonBodyMass.csv
SPLIT     = data/split/train.csv
TUNE_XGB  = predictive_models/results/tuning_study.json
TUNE_GPB  = predictive_models/results/tuning_study_gpboost.json
TUNE_EE   = predictive_models/results/tuning_study_ee.json

.PHONY: all fetch split \
        tune tune-xgboost tune-gpboost tune-ee \
        train train-xgboost train-gpboost train-ee \
        artifacts clean-tune

all: artifacts

# ---- Fetch updated source data -----------------------------------------------
$(LOCAL_CSV): $(DB_CSV)
	python scripts/fetch_source_data.py

# ---- Train/test split ---------------------------------------------------------
$(SPLIT): $(LOCAL_CSV)
	python data_partition/data_split_visualization.py

split: $(SPLIT)

# ---- Hyperparameter tuning (independent; use -j3 to run in parallel) ---------
$(TUNE_XGB): $(SPLIT)
	python predictive_models/tune_hyperparameters.py --model xgboost

$(TUNE_GPB): $(SPLIT)
	python predictive_models/tune_hyperparameters.py --model gpboost

$(TUNE_EE): $(SPLIT)
	python predictive_models/tune_hyperparameters.py --model ee

tune-xgboost: $(TUNE_XGB)
tune-gpboost: $(TUNE_GPB)
tune-ee: $(TUNE_EE)
tune: tune-xgboost tune-gpboost tune-ee

# ---- Training (each reads best params from its tuning JSON at runtime) --------
train-xgboost: $(TUNE_XGB)
	python predictive_models/decision_tree.py

train-gpboost: $(TUNE_GPB)
	python predictive_models/gpboost_model.py

train-ee: $(TUNE_EE)
	python predictive_models/entity_embeddings_model.py

train: train-xgboost train-gpboost train-ee

# ---- Artifact export ----------------------------------------------------------
artifacts: train
	python scripts/export_artifacts.py

# ---- Discard stale tuning state (re-run after data changes) ------------------
clean-tune:
	rm -f predictive_models/results/tuning.db \
	      predictive_models/results/tuning_study.json \
	      predictive_models/results/tuning_gpboost.db \
	      predictive_models/results/tuning_study_gpboost.json \
	      predictive_models/results/tuning_ee.db \
	      predictive_models/results/tuning_study_ee.json
