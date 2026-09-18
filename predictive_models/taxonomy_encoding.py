"""
Single source of truth for the taxonomy feature contract shared by training,
tuning, artifact export and the analysis scripts.

The contract
------------
* ``TAXONOMY_COLS`` is the full taxonomy (kingdom .. species).  It is what the
  packages resolve, look up in the training dictionary and use for source-rank
  inference.
* ``MODEL_FEATURES`` is the subset the models are trained on: kingdom .. genus.
  Species is deliberately excluded.  The training table has one row per
  species, so a species feature can only memorise individual rows; at
  inference every queried species is by construction absent from training
  (known species are answered from the dictionary), so the feature carries no
  information there and only soaks up signal that belongs to the hierarchy.
  Inference code must never assume the feature order; it must reorder its
  input to the model's own ``feature_names``.
* Each column's vocabulary is ``["UNK"] + sorted(unique training values)``.
  Because the list is sorted with UNK first, the alphabetical order *is* the
  training-time integer-code order, so ``categories.json`` (written from this
  vocabulary) can be consumed directly as pandas categories / R factor levels.
* The vocabulary is built from the training split only.  Taxa that appear only
  in the test split are mapped to UNK at evaluation time, which mirrors what
  happens to unseen taxa at inference time.
* Values are ASCII-normalised upstream (data_partition), NaN and unseen values
  map to UNK.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
MODEL_FEATURES = ["kingdom", "phylum", "class", "order", "family", "genus"]

UNK = "UNK"

# For each rank, the finer *model* features that are masked to UNK when
# computing rank-stratified conformal residuals.  A genus-level query masks
# nothing (species is not a feature), so its residuals equal the pooled ones.
RANKS_FINER = {
    "genus": [],
    "family": ["genus"],
    "order": ["family", "genus"],
    "class": ["order", "family", "genus"],
    "phylum": ["class", "order", "family", "genus"],
    "kingdom": ["phylum", "class", "order", "family", "genus"],
}


def build_vocab(train_df: pd.DataFrame) -> dict[str, list[str]]:
    """Per-column vocabulary from the training split; UNK is always code 0."""
    vocab = {}
    for col in MODEL_FEATURES:
        values = set(train_df[col].dropna().astype(str)) - {UNK}
        vocab[col] = [UNK] + sorted(values)
    return vocab


def _to_vocab_strings(series: pd.Series, categories: list[str]) -> pd.Series:
    s = series.fillna(UNK).astype(str)
    return s.where(s.isin(set(categories)), other=UNK)


def encode_categorical(df: pd.DataFrame, vocab: dict[str, list[str]]) -> pd.DataFrame:
    """
    Return ``df[MODEL_FEATURES]`` with each column as a ``pd.Categorical`` whose
    categories are exactly ``vocab[col]`` (so ``.cat.codes`` equals the
    training integer code).  Missing columns, NaN and unseen values map to UNK.
    Suitable for ``XGBRegressor(enable_categorical=True)`` and
    ``xgb.DMatrix(..., enable_categorical=True)``.
    """
    out = pd.DataFrame(index=df.index)
    for col in MODEL_FEATURES:
        raw = df[col] if col in df.columns else pd.Series(UNK, index=df.index)
        out[col] = pd.Categorical(_to_vocab_strings(raw, vocab[col]), categories=vocab[col])
    return out


def encode_codes(df: pd.DataFrame, vocab: dict[str, list[str]]) -> np.ndarray:
    """Integer codes as an ``(n, len(MODEL_FEATURES))`` int64 array; unseen -> 0."""
    cat = encode_categorical(df, vocab)
    return np.column_stack([cat[col].cat.codes.to_numpy(dtype=np.int64) for col in MODEL_FEATURES])


def validate_vocab(vocab: dict[str, list[str]]) -> None:
    """Raise if a vocabulary violates the contract (UNK first, sorted, unique)."""
    if set(vocab) != set(MODEL_FEATURES):
        raise ValueError(f"vocab columns {sorted(vocab)} != MODEL_FEATURES {MODEL_FEATURES}")
    for col in MODEL_FEATURES:
        cats = vocab[col]
        if cats[0] != UNK:
            raise ValueError(f"{col}: first category must be {UNK!r}, got {cats[0]!r}")
        rest = cats[1:]
        if rest != sorted(rest):
            raise ValueError(f"{col}: categories after UNK must be sorted alphabetically")
        if len(set(cats)) != len(cats):
            raise ValueError(f"{col}: duplicate categories")
