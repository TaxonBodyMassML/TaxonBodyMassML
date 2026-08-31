"""
Two-stage entity embeddings model.

Stage 1: PyTorch MLP with per-taxonomy-column embedding layers.
         Learns dense representations; singleton species share gradient signal
         through shared genus/family/order/class embedding tables.
Stage 2: XGBoost trained on the extracted embedding vectors (continuous features,
         no min_child_weight constraint).

Run from any directory:
    python predictive_models/entity_embeddings_model.py

Outputs (in artifacts/):
    embeddings.json  -- per-column embedding lookup {col: {value: [...], "UNK": [...]}}
    model_ee.ubj        -- Stage 2 XGBoost in binary UBJSON format
    calibration_ee.json -- {"residuals": [...]} conformal calibration residuals

Requirements:
    pip install torch>=2.0 xgboost>=1.7
"""

import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from torch.optim.lr_scheduler import OneCycleLR
from torch.utils.data import DataLoader, TensorDataset

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAIN_CSV = REPO_ROOT / "data" / "split" / "train.csv"
TEST_CSV = REPO_ROOT / "data" / "split" / "test.csv"
OUT_DIR = REPO_ROOT / "artifacts"
RESULTS_DIR = REPO_ROOT / "predictive_models" / "results"
OUT_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
EMB_DIMS = {
    "kingdom": 4,
    "phylum": 8,
    "class": 8,
    "order": 16,
    "family": 16,
    "genus": 32,
    "species": 32,
}
TOTAL_DIM = sum(EMB_DIMS.values())  # 116

STAGE1_EPOCHS = 100
STAGE1_BATCH_SIZE = 256
STAGE1_LR = 1e-3

_TUNING_JSON = RESULTS_DIR / "tuning_study_ee.json"
_DEFAULT_STAGE2 = {
    "n_estimators": 400,
    "max_depth": 8,
    "learning_rate": 0.1,
    "subsample": 0.8,
}


def _load_best_params():
    if _TUNING_JSON.exists():
        with open(_TUNING_JSON) as f:
            return json.load(f)["best_params"]
    return dict(_DEFAULT_STAGE2)


STAGE2_PARAMS = {
    "objective": "reg:absoluteerror",
    "random_state": 42,
    **_load_best_params(),
}


# ---------------------------------------------------------------------------
# Vocabulary builder
# ---------------------------------------------------------------------------


def build_vocabs(train_df: pd.DataFrame) -> dict[str, list[str]]:
    """Build per-column vocabulary from training data; UNK always at index 0."""
    vocabs = {}
    for col in TAXONOMY_COLS:
        unique_vals = sorted(train_df[col].dropna().astype(str).unique())
        vocabs[col] = ["UNK"] + unique_vals  # 0 = UNK
    return vocabs


def encode(df: pd.DataFrame, vocabs: dict[str, list[str]]) -> np.ndarray:
    """Map each column to its integer index; unknowns → 0 (UNK)."""
    n = len(df)
    out = np.zeros((n, len(TAXONOMY_COLS)), dtype=np.int64)
    for j, col in enumerate(TAXONOMY_COLS):
        v2i = {v: i for i, v in enumerate(vocabs[col])}
        vals = df[col].fillna("UNK").astype(str)
        out[:, j] = [v2i.get(v, 0) for v in vals]
    return out


# ---------------------------------------------------------------------------
# Stage 1: PyTorch embedding MLP
# ---------------------------------------------------------------------------


class EmbeddingMLP(nn.Module):
    def __init__(self, vocabs: dict[str, list[str]]):
        super().__init__()
        self.emb_layers = nn.ModuleList(
            [
                nn.Embedding(len(vocabs[col]), EMB_DIMS[col], padding_idx=None)
                for col in TAXONOMY_COLS
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
        embs = [self.emb_layers[j](x[:, j]) for j in range(len(TAXONOMY_COLS))]
        h = torch.cat(embs, dim=1)
        return self.mlp(h).squeeze(1)

    def get_embeddings(
        self, vocabs: dict[str, list[str]]
    ) -> dict[str, dict[str, list[float]]]:  # noqa: E501
        """Extract embedding lookup tables; UNK = mean of all column embeddings."""
        result = {}
        for j, col in enumerate(TAXONOMY_COLS):
            W = self.emb_layers[j].weight.detach().cpu().numpy()  # (vocab, dim)
            v2e = {v: W[i].tolist() for i, v in enumerate(vocabs[col])}
            # Override UNK with the mean of all non-UNK embeddings (index 0 was random init)  # noqa: E501
            v2e["UNK"] = W[1:].mean(axis=0).tolist() if len(W) > 1 else W[0].tolist()
            result[col] = v2e
        return result


def train_stage1(
    X_codes: np.ndarray,
    y: np.ndarray,
    vocabs: dict[str, list[str]],
    device: torch.device,
) -> EmbeddingMLP:
    model = EmbeddingMLP(vocabs).to(device)
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
# Stage 2: build embedding feature matrix for XGBoost
# ---------------------------------------------------------------------------


def make_emb_features(
    df: pd.DataFrame, embeddings: dict[str, dict[str, list[float]]]
) -> np.ndarray:
    n = len(df)
    X = np.zeros((n, TOTAL_DIM), dtype=np.float32)
    offset = 0
    for col in TAXONOMY_COLS:
        dim = EMB_DIMS[col]
        col_embs = embeddings[col]
        unk_vec = np.array(col_embs["UNK"], dtype=np.float32)
        vals = df[col].fillna("UNK").astype(str)
        for i, val in enumerate(vals):
            vec = col_embs.get(val, unk_vec)
            X[i, offset : offset + dim] = vec
        offset += dim
    return X


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

print("Loading data...")
train = pd.read_csv(TRAIN_CSV)
test = pd.read_csv(TEST_CSV)
train["mass_g"] = np.log10(train["mass_g"])
test["mass_g"] = np.log10(test["mass_g"])

y_train = train["mass_g"].values
y_test = test["mass_g"].values

print(f"  Training: {len(y_train):,}  Test: {len(y_test):,}")

# Build vocabulary from training data only (test values become UNK if unseen)
vocabs = build_vocabs(train)
vocab_sizes = {col: len(vocabs[col]) for col in TAXONOMY_COLS}
print("  Vocab sizes:", vocab_sizes)

X_codes_train = encode(train, vocabs)
X_codes_test = encode(test, vocabs)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"  Device: {device}")


# ---------------------------------------------------------------------------
# Stage 1: Train MLP on full training set → extract embeddings
# ---------------------------------------------------------------------------
print("Stage 1: Training embedding MLP...")
mlp = train_stage1(X_codes_train, y_train, vocabs, device)

# Evaluate Stage 1 MAE on test set
with torch.no_grad():
    X_t = torch.from_numpy(X_codes_test).long().to(device)
    preds1 = mlp(X_t).cpu().numpy()
mae1 = float(mean_absolute_error(y_test, preds1))
print(f"  Stage 1 test MAE = {mae1:.4f} log10 units")

# Extract embeddings
print("Extracting embedding lookup tables...")
embeddings = mlp.get_embeddings(vocabs)

embeddings_path = OUT_DIR / "embeddings.json"
with open(embeddings_path, "w") as f:
    json.dump(embeddings, f)
size_mb = embeddings_path.stat().st_size / 1e6
print(f"  Saved embeddings → {embeddings_path}  ({size_mb:.1f} MB)")


# ---------------------------------------------------------------------------
# Stage 2a: Conformal calibration (80/20 split of training set)
# ---------------------------------------------------------------------------
print("Stage 2 conformal calibration (80/20 split)...")
idx_all = np.arange(len(y_train))
idx_tr2, idx_cal = train_test_split(idx_all, test_size=0.2, random_state=42)

train_sub = train.iloc[idx_tr2].reset_index(drop=True)
calib_df = train.iloc[idx_cal].reset_index(drop=True)
y_tr2 = y_train[idx_tr2]
y_cal = y_train[idx_cal]

# Stage 1 on 80% subset
mlp_calib = train_stage1(X_codes_train[idx_tr2], y_tr2, vocabs, device)
embs_calib = mlp_calib.get_embeddings(vocabs)

# Stage 2 XGBoost on 80% embeddings
X_emb_tr2 = make_emb_features(train_sub, embs_calib)
X_emb_cal = make_emb_features(calib_df, embs_calib)
m2_calib = xgb.XGBRegressor(**STAGE2_PARAMS)
m2_calib.fit(X_emb_tr2, y_tr2)

cal_preds = m2_calib.predict(X_emb_cal)
calib_residuals = sorted(float(r) for r in np.abs(y_cal - cal_preds))

calibration_path = OUT_DIR / "calibration_ee.json"
with open(calibration_path, "w") as f:
    json.dump({"residuals": calib_residuals}, f)
print(f"  {len(calib_residuals)} residuals → {calibration_path}")
print(f"  q90 = {float(np.quantile(calib_residuals, 0.90)):.4f} log10 units")

# Rank-stratified calibration: set finer-rank columns to "UNK" in calib_df
# before building embedding features.  The UNK embedding is used for masked
# columns, matching the inference condition for coarser-rank queries.
print("Building rank-stratified calibration residuals for EntityEmbeddings...")
RANKS_FINER_EE = {
    "genus": ["species"],
    "family": ["genus", "species"],
    "order": ["family", "genus", "species"],
    "class": ["order", "family", "genus", "species"],
    "phylum": ["class", "order", "family", "genus", "species"],
    "kingdom": ["phylum", "class", "order", "family", "genus", "species"],
}
by_rank_ee = {}
for rank, finer_cols in RANKS_FINER_EE.items():
    calib_masked = calib_df.copy()
    for col in finer_cols:
        if col in calib_masked.columns:
            calib_masked[col] = "UNK"
    X_emb_cal_masked = make_emb_features(calib_masked, embs_calib)
    res_rank = np.abs(y_cal - m2_calib.predict(X_emb_cal_masked))
    by_rank_ee[rank] = sorted(float(r) for r in res_rank)
    print(f"  {rank}: q90={float(np.quantile(res_rank, 0.90)):.4f}")

by_rank_ee_path = OUT_DIR / "calibration_by_rank_ee.json"
with open(by_rank_ee_path, "w") as f:
    json.dump(by_rank_ee, f)
print(f"  Saved → {by_rank_ee_path}")


# ---------------------------------------------------------------------------
# Stage 2b: Train final Stage 2 XGBoost on full training set embeddings
# ---------------------------------------------------------------------------
print("Stage 2: Training XGBoost on full embedding features...")
X_emb_train = make_emb_features(train, embeddings)
X_emb_test = make_emb_features(test, embeddings)

model_ee = xgb.XGBRegressor(**STAGE2_PARAMS)
model_ee.fit(X_emb_train, y_train)

log_preds_test = model_ee.predict(X_emb_test)
mae = float(mean_absolute_error(y_test, log_preds_test))
rmse = float(np.sqrt(mean_squared_error(y_test, log_preds_test)))
r2 = float(r2_score(y_test, log_preds_test))
print(f"  Test  MAE={mae:.4f}  RMSE={rmse:.4f}  R²={r2:.4f}  (log10 space)")

model_ee_path = OUT_DIR / "model_ee.ubj"
booster = model_ee.get_booster()
booster.save_model(str(model_ee_path))
print(f"  Saved Stage 2 XGBoost → {model_ee_path}")


# ---------------------------------------------------------------------------
# Save metrics
# ---------------------------------------------------------------------------
metrics = {
    "method": "EntityEmbeddings",
    "r2": r2,
    "rmse": rmse,
    "mae": mae,
    "stage1_mae": mae1,
    "n_train": int(len(y_train)),
    "n_test": int(len(y_test)),
    "log10_space": True,
    "stage1_epochs": STAGE1_EPOCHS,
    "stage1_batch": STAGE1_BATCH_SIZE,
    "stage1_lr": STAGE1_LR,
    "emb_dims": EMB_DIMS,
    "total_emb_dim": TOTAL_DIM,
    "stage2_params": STAGE2_PARAMS,
    "vocab_sizes": vocab_sizes,
    "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
metrics_path = RESULTS_DIR / "metrics_ee.json"
with open(metrics_path, "w") as f:
    json.dump(metrics, f, indent=2)
print(f"Metrics → {metrics_path}")
print("Done.")
