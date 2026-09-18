import argparse
import datetime
import json
import os
import sys
from pathlib import Path

import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from sklearn.model_selection import KFold

sys.path.insert(0, str(Path(__file__).resolve().parent))
from taxonomy_encoding import (  # noqa: E402
    MODEL_FEATURES,
    build_vocab,
    encode_categorical,
    encode_codes,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

N_TRIALS = int(os.environ.get("TBM_N_TRIALS", 100))
N_FOLDS = 5
SEED = 42


# ---------------------------------------------------------------------------
# Entity Embeddings helpers (copied from entity_embeddings_model.py)
# ---------------------------------------------------------------------------

EMB_DIMS = {
    "kingdom": 4,
    "phylum": 8,
    "class": 8,
    "order": 16,
    "family": 16,
    "genus": 32,
}
TOTAL_DIM = sum(EMB_DIMS.values())  # 84


def make_emb_features(df, embeddings):
    """Build (n, TOTAL_DIM) float32 matrix from embedding lookup tables."""
    n = len(df)
    X = np.zeros((n, TOTAL_DIM), dtype=np.float32)
    offset = 0
    for col in MODEL_FEATURES:
        dim = EMB_DIMS[col]
        col_embs = embeddings[col]
        unk_vec = np.array(col_embs["UNK"], dtype=np.float32)
        vals = df[col].fillna("UNK").astype(str)
        for i, val in enumerate(vals):
            vec = col_embs.get(val, unk_vec)
            X[i, offset : offset + dim] = vec
        offset += dim
    return X


def _build_embedding_mlp_and_train(X_codes, y, vocabs, device):
    """Train a PyTorch EmbeddingMLP and return (model, get_embeddings_fn)."""
    import torch
    import torch.nn as nn
    from torch.optim.lr_scheduler import OneCycleLR
    from torch.utils.data import DataLoader, TensorDataset

    STAGE1_EPOCHS = 100
    STAGE1_BATCH_SIZE = 256
    STAGE1_LR = 1e-3

    class EmbeddingMLP(nn.Module):
        def __init__(self):
            super().__init__()
            self.emb_layers = nn.ModuleList(
                [
                    nn.Embedding(len(vocabs[col]), EMB_DIMS[col], padding_idx=None)
                    for col in MODEL_FEATURES
                ]
            )
            self.mlp = nn.Sequential(
                nn.Linear(TOTAL_DIM, 64),
                nn.ReLU(),
                nn.Linear(64, 32),
                nn.ReLU(),
                nn.Linear(32, 1),
            )

        def forward(self, x):
            embs = [self.emb_layers[j](x[:, j]) for j in range(len(MODEL_FEATURES))]
            h = torch.cat(embs, dim=1)
            return self.mlp(h).squeeze(1)

        def get_embeddings(self):
            result = {}
            for j, col in enumerate(MODEL_FEATURES):
                W = self.emb_layers[j].weight.detach().cpu().numpy()
                v2e = {v: W[i].tolist() for i, v in enumerate(vocabs[col])}
                v2e["UNK"] = (  # noqa: E501
                    W[1:].mean(axis=0).tolist() if len(W) > 1 else W[0].tolist()
                )
                result[col] = v2e
            return result

    model = EmbeddingMLP().to(device)
    opt = torch.optim.Adam(model.parameters(), lr=STAGE1_LR)
    X_t = torch.from_numpy(X_codes).long().to(device)
    y_t = torch.from_numpy(y.astype(np.float32)).to(device)
    ds = TensorDataset(X_t, y_t)
    dl = DataLoader(ds, batch_size=STAGE1_BATCH_SIZE, shuffle=True, drop_last=False)
    sched = OneCycleLR(
        opt, max_lr=STAGE1_LR, epochs=STAGE1_EPOCHS, steps_per_epoch=len(dl)
    )  # noqa: E501
    loss_fn = nn.L1Loss()

    model.train()
    for epoch in range(1, STAGE1_EPOCHS + 1):
        total_loss = 0.0
        for xb, yb in dl:
            opt.zero_grad()
            pred = model(xb)
            loss = loss_fn(pred, yb)
            loss.backward()
            opt.step()
            sched.step()
            total_loss += loss.item() * len(xb)
        if epoch % 10 == 0:
            print(f"  Epoch {epoch:3d}/{STAGE1_EPOCHS}  MAE={total_loss/len(ds):.4f}")

    model.eval()
    return model


# ---------------------------------------------------------------------------
# XGBoost tuner
# ---------------------------------------------------------------------------


def tune_xgboost():
    train = pd.read_csv(REPO_ROOT / "data" / "split" / "train.csv")
    train["mass_g"] = np.log10(train["mass_g"])

    y_full = train["mass_g"]
    # Same encoding contract as decision_tree.py: native categorical features,
    # vocabulary from the training split only (UNK first, then sorted).
    x_full = encode_categorical(train, build_vocab(train))

    kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)

    def objective(trial):
        params = dict(
            objective="reg:absoluteerror",
            enable_categorical=True,
            random_state=SEED,
            n_estimators=trial.suggest_int("n_estimators", 200, 900, step=50),
            max_depth=trial.suggest_int("max_depth", 5, 50),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.30, log=True),
            subsample=trial.suggest_float("subsample", 0.5, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
            gamma=trial.suggest_float("gamma", 0.0, 1.0),
            min_child_weight=trial.suggest_int("min_child_weight", 1, 10),
        )
        fold_maes = []
        for train_idx, val_idx in kf.split(x_full):
            model = xgb.XGBRegressor(**params)
            model.fit(x_full.iloc[train_idx], y_full.iloc[train_idx])
            preds = model.predict(x_full.iloc[val_idx])
            fold_maes.append(float(np.mean(np.abs(y_full.iloc[val_idx] - preds))))
        return float(np.mean(fold_maes))

    sampler = optuna.samplers.TPESampler(seed=SEED)
    study = optuna.create_study(
        study_name="tbml_tuning",
        storage="sqlite:///" + str(RESULTS_DIR / "tuning.db"),
        direction="minimize",
        sampler=sampler,
        load_if_exists=True,
    )
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

    results = {
        "best_params": study.best_params,
        "best_cv_mae": study.best_value,
        "n_trials": N_TRIALS,
        "n_folds": N_FOLDS,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "current_params": {
            "n_estimators": 600,
            "max_depth": 40,
            "learning_rate": 0.05,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "gamma": 0,
            "min_child_weight": 1,
        },
        "all_trials": [
            {"number": t.number, "params": t.params, "cv_mae": t.value}
            for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
        ],
    }
    out = RESULTS_DIR / "tuning_study.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nBest CV MAE : {study.best_value:.4f} log10")
    print(f"Best params : {study.best_params}")
    print(f"Saved       -> {out}")


# ---------------------------------------------------------------------------
# Entity Embeddings Stage 2 tuner
# ---------------------------------------------------------------------------


def tune_ee():
    import torch

    torch.set_num_threads(1)  # prevent libomp conflict with xgboost/sklearn OpenMP

    train = pd.read_csv(REPO_ROOT / "data" / "split" / "train.csv")
    train["mass_g"] = np.log10(train["mass_g"])
    y_full_ee = train["mass_g"].values

    vocabs = build_vocab(train)
    X_codes = encode_codes(train, vocabs)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print("Stage 1: pre-training MLP for EE tuning (done once)...")
    mlp = _build_embedding_mlp_and_train(X_codes, y_full_ee, vocabs, device)
    embeddings = mlp.get_embeddings()
    X_emb_full = make_emb_features(train, embeddings)

    kf = KFold(n_splits=N_FOLDS, shuffle=True, random_state=SEED)

    def objective(trial):
        params = dict(
            objective="reg:absoluteerror",
            random_state=SEED,
            n_estimators=trial.suggest_int("n_estimators", 200, 800, step=50),
            max_depth=trial.suggest_int("max_depth", 4, 15),
            learning_rate=trial.suggest_float("learning_rate", 0.01, 0.30, log=True),
            subsample=trial.suggest_float("subsample", 0.5, 1.0),
            colsample_bytree=trial.suggest_float("colsample_bytree", 0.5, 1.0),
            min_child_weight=trial.suggest_int("min_child_weight", 1, 10),
        )
        fold_maes = []
        for train_idx, val_idx in kf.split(X_emb_full):
            model = xgb.XGBRegressor(**params)
            model.fit(X_emb_full[train_idx], y_full_ee[train_idx])
            preds = model.predict(X_emb_full[val_idx])
            fold_maes.append(float(np.mean(np.abs(y_full_ee[val_idx] - preds))))
        return float(np.mean(fold_maes))

    sampler = optuna.samplers.TPESampler(seed=SEED)
    study = optuna.create_study(
        study_name="tbml_ee",
        storage="sqlite:///" + str(RESULTS_DIR / "tuning_ee.db"),
        direction="minimize",
        sampler=sampler,
        load_if_exists=True,
    )
    study.optimize(objective, n_trials=N_TRIALS, show_progress_bar=True)

    results = {
        "best_params": study.best_params,
        "best_cv_mae": study.best_value,
        "n_trials": N_TRIALS,
        "n_folds": N_FOLDS,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "current_params": {
            "n_estimators": 400,
            "max_depth": 8,
            "learning_rate": 0.1,
            "subsample": 0.8,
        },
        "all_trials": [
            {"number": t.number, "params": t.params, "cv_mae": t.value}
            for t in study.trials
            if t.state == optuna.trial.TrialState.COMPLETE
        ],
    }
    out = RESULTS_DIR / "tuning_study_ee.json"
    with open(out, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nBest CV MAE : {study.best_value:.4f} log10")
    print(f"Best params : {study.best_params}")
    print(f"Saved       -> {out}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hyperparameter tuning for TaxonBodyMassML models."
    )
    parser.add_argument(
        "--model",
        choices=["xgboost", "ee"],
        default="xgboost",
        help="Which model to tune (default: xgboost)",
    )
    args = parser.parse_args()

    if args.model == "xgboost":
        tune_xgboost()
    elif args.model == "ee":
        tune_ee()
