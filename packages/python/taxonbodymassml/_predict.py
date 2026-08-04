"""
Prediction logic: UNK mapping, XGBoost inference, conformal intervals.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb

from ._lookup import TAXONOMY_COLS, lookup_taxonomy
from ._model import _ensure_artifacts, load_calibration, load_categories, load_model

_TAXONOMY_INPUT_COLS = [
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species_resolved",
]


# ---------------------------------------------------------------------------
# CI level resolver
# ---------------------------------------------------------------------------
def _resolve_ci_level(confidence_interval) -> Optional[float]:
    if confidence_interval is False:
        return None
    if confidence_interval is True:
        return 0.90
    ci = float(confidence_interval)
    if not (0.0 < ci < 1.0):
        raise ValueError(
            "confidence_interval must be False, True, or a float in (0, 1). "
            f"Got: {confidence_interval!r}"
        )
    return ci


# ---------------------------------------------------------------------------
# UNK mapping
# ---------------------------------------------------------------------------
def _apply_unk_mapping(df: pd.DataFrame, categories: dict[str, list[str]]) -> pd.DataFrame:
    """Replace unknown category values with 'UNK' and set category dtype."""
    col_map = {
        "kingdom": "kingdom",
        "phylum": "phylum",
        "class": "class",
        "order": "order",
        "family": "family",
        "genus": "genus",
        "species_resolved": "species",
    }
    # Select only the taxonomy input columns to avoid duplicate column names
    # (taxonomy_df contains both 'species' (input name) and 'species_resolved').
    cols = [c for c in col_map if c in df.columns]
    renamed = df[cols].rename(columns=col_map)

    for col in TAXONOMY_COLS:
        valid = set(categories.get(col, []))
        mapped = renamed[col].where(renamed[col].isin(valid), other="UNK")
        renamed[col] = pd.Categorical(mapped, categories=categories[col])

    return renamed[TAXONOMY_COLS]


# ---------------------------------------------------------------------------
# XGBoost predictor
# ---------------------------------------------------------------------------
def _predict_xgboost(
    taxonomy_df: pd.DataFrame,
    level: Optional[float],
    include_taxonomy: bool,
    input_names: list[str],
) -> pd.DataFrame:
    _ensure_artifacts()
    model = load_model()
    categories = load_categories()

    X = _apply_unk_mapping(taxonomy_df, categories)
    dmat = xgb.DMatrix(X, enable_categorical=True)
    log_preds = model.predict(dmat)

    rows = []
    residuals = load_calibration() if level is not None else None
    q = float(np.quantile(residuals, level)) if residuals is not None else None

    for i, (name, log_pred) in enumerate(zip(input_names, log_preds)):
        row: dict = {"taxon": name, "mass_g": float(10**log_pred)}
        if level is not None:
            row["lower_bound"] = float(10 ** (log_pred - q))
            row["upper_bound"] = float(10 ** (log_pred + q))
            row["confidence"] = level
        if include_taxonomy:
            for col in _TAXONOMY_INPUT_COLS:
                row[col] = taxonomy_df[col].iloc[i] if col in taxonomy_df.columns else None
        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------
_METHODS = {
    "XGBoost": _predict_xgboost,
}


# ---------------------------------------------------------------------------
# Public: predict_mass()
# ---------------------------------------------------------------------------
def predict_mass(
    species,
    confidence_interval=False,
    method: str = "XGBoost",
    include_taxonomy: bool = False,
    fuzzy_match_name: bool = False,
) -> pd.DataFrame:
    """Predict body mass for one or more species.

    Parameters
    ----------
    species : str, list of str, or pd.DataFrame
        Scientific name(s) to predict.  Pass a ``pd.DataFrame`` with columns
        ``kingdom``, ``phylum``, ``class``, ``order``, ``family``, ``genus``,
        ``species_resolved`` to skip the taxonomy lookup step.
    confidence_interval : bool or float
        ``False`` — no interval (default).
        ``True`` — 90% conformal prediction interval.
        ``float`` in (0, 1) — interval at that coverage level.
    method : str
        Prediction method.  Currently only ``"XGBoost"`` is supported.
    include_taxonomy : bool
        If ``True``, include the resolved taxonomy columns in the output.
    fuzzy_match_name : bool
        If ``True``, species names are first corrected via the GBIF
        species-match API before taxonomy lookup, tolerating misspellings and
        minor name variants.  A ``matched_name`` column is appended to the
        output: it contains the originally entered name when a correction was
        applied or no GBIF match was found; ``None`` when the name was already
        canonical.  Default ``False`` (exact name matching).  Ignored when
        ``species`` is a ``pd.DataFrame``.

    Returns
    -------
    pd.DataFrame
        Always includes ``taxon`` and ``mass_g`` (grams).
        With ``confidence_interval != False``: also ``lower_bound``,
        ``upper_bound``, ``confidence``.
        With ``include_taxonomy=True``: also ``kingdom`` … ``species_resolved``.
        With ``fuzzy_match_name=True``: also ``matched_name`` (the originally
        entered name if corrected or unmatched; ``None`` if no correction was
        needed).
        Rows for unresolvable species have ``NaN`` for numeric columns.
    """
    if method not in _METHODS:
        raise ValueError(f"Unknown method {method!r}. Available: {list(_METHODS)}")
    level = _resolve_ci_level(confidence_interval)

    # ---- Input handling ------------------------------------------------
    if isinstance(species, pd.DataFrame):
        required = set(_TAXONOMY_INPUT_COLS)
        missing = required - set(species.columns)
        if missing:
            raise ValueError(f"Input DataFrame is missing taxonomy columns: {sorted(missing)}")
        taxonomy_df = species.reset_index(drop=True)
        input_names = taxonomy_df.get("species", taxonomy_df["species_resolved"]).tolist()
        matched_names = None
    else:
        if isinstance(species, str):
            names = [species]
        else:
            names = list(species)
        if fuzzy_match_name:
            from ._fuzzy import fuzzy_lookup_taxonomy  # local import avoids circular dep

            tax_full = fuzzy_lookup_taxonomy(names)
            corrected = tax_full["matched_name"].notna() & (
                tax_full["matched_name"] != tax_full["input_name"]
            )
            no_match = tax_full["matched_name"].isna()
            input_names = (
                tax_full["matched_name"]
                .where(corrected, tax_full["input_name"].where(~no_match, other=None))
                .tolist()
            )
            matched_names = tax_full["input_name"].where(corrected | no_match, other=None).tolist()
            taxonomy_df = tax_full.drop(columns=["input_name", "matched_name"])
        else:
            taxonomy_df = lookup_taxonomy(names)
            input_names = taxonomy_df["species"].tolist()
            matched_names = None

    # ---- Empty input: return zero-row DataFrame with correct schema --------
    if len(taxonomy_df) == 0:
        cols = ["taxon", "mass_g"]
        if level is not None:
            cols += ["lower_bound", "upper_bound", "confidence"]
        if include_taxonomy:
            cols += _TAXONOMY_INPUT_COLS
        if matched_names is not None:
            cols += ["matched_name"]
        return pd.DataFrame(columns=cols)

    # ---- Rows with failed lookup (all None) get NaN predictions ----------
    resolved_mask = taxonomy_df["species_resolved"].notna()

    if not resolved_mask.any():
        warnings.warn("No species could be resolved; returning all-NaN result.", stacklevel=2)

    resolved_pos = [i for i, ok in enumerate(resolved_mask) if ok]
    unresolved_pos = [i for i, ok in enumerate(resolved_mask) if not ok]

    result_rows = []
    if resolved_mask.any():
        sub = taxonomy_df[resolved_mask].reset_index(drop=True)
        sub_names = [input_names[i] for i in resolved_pos]
        good_df = _METHODS[method](sub, level, include_taxonomy, sub_names)
        good_df["_orig_idx"] = resolved_pos
        result_rows.append(good_df)

    if not resolved_mask.all():
        nan_names = [input_names[i] for i in unresolved_pos]
        nan_rows = [{"taxon": n, "mass_g": float("nan")} for n in nan_names]
        if level is not None:
            for r in nan_rows:
                r.update(
                    {
                        "lower_bound": float("nan"),
                        "upper_bound": float("nan"),
                        "confidence": level,
                    }
                )
        if include_taxonomy:
            for r in nan_rows:
                r.update({c: None for c in _TAXONOMY_INPUT_COLS})
        nan_df = pd.DataFrame(nan_rows)
        nan_df["_orig_idx"] = unresolved_pos
        result_rows.append(nan_df)

    out = pd.concat(result_rows, ignore_index=True)
    out = out.sort_values("_orig_idx").drop(columns="_orig_idx").reset_index(drop=True)

    if matched_names is not None:
        out["matched_name"] = matched_names

    return out
