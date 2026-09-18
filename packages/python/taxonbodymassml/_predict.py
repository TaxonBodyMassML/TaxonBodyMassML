"""
Prediction logic: UNK mapping, XGBoost inference, conformal intervals.
"""

from __future__ import annotations

import unicodedata
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import xgboost as xgb

from ._lookup import TAXONOMY_COLS, lookup_taxonomy
from ._model import (
    _ensure_artifacts,
    load_calibration,
    load_calibration_by_rank,
    load_calibration_by_rank_ee,
    load_calibration_ee,
    load_categories,
    load_embeddings,
    load_lookup,
    load_model,
    load_model_ee,
)

_TAXONOMY_INPUT_COLS = [
    "kingdom",
    "phylum",
    "class",
    "order",
    "family",
    "genus",
    "species_resolved",
]

_RANK_ORDER = ["genus", "family", "order", "class", "phylum", "kingdom"]

# Model features: kingdom .. genus.  Species is not a feature (the training
# table has one row per species, so it could only memorise; every queried
# species is unseen by construction and known species come from the lookup
# dictionary).  It is still consulted for genus promotion below.
_MODEL_FEATURES = [c for c in TAXONOMY_COLS if c != "species"]


# ---------------------------------------------------------------------------
# CI level resolver / interval method validator
# ---------------------------------------------------------------------------
def _resolve_interval_method(interval_method: str) -> str:
    valid = {"stratified", "pooled"}
    if interval_method not in valid:
        raise ValueError(
            f"interval_method must be 'stratified' or 'pooled'. "
            f"Got: {interval_method!r}"  # noqa: E501
        )
    return interval_method


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
# Helpers
# ---------------------------------------------------------------------------
def _ascii_normalize(x):
    if pd.isna(x):
        return None
    normalized = unicodedata.normalize("NFKD", str(x))
    return normalized.encode("ascii", "ignore").decode("ascii")


# GBIF v2 uses clade-based kingdom names; training data was built with the
# older GBIF v1 / Catalogue of Life names.
_GBIF_KINGDOM_NORM: dict[str, str] = {
    "Metazoa": "Animalia",
    "Plantae": "Viridiplantae",
}


# ---------------------------------------------------------------------------
# UNK mapping
# ---------------------------------------------------------------------------
def _apply_unk_mapping(  # noqa: E501
    df: pd.DataFrame, categories: dict[str, list[str]]
) -> pd.DataFrame:
    """Model feature frame (kingdom..genus) as pd.Categorical with training categories."""
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

    for col in _MODEL_FEATURES:
        col_data = renamed[col].apply(_ascii_normalize)
        if col == "kingdom":
            col_data = col_data.map(lambda x: _GBIF_KINGDOM_NORM.get(x, x))
        if col == "genus":
            # Genus names queried via NCBI land in species_resolved with genus
            # left as "UNK". Promote them to the correct slot.
            sp_data = renamed["species"].apply(_ascii_normalize)
            genus_vocab = set(categories.get("genus", [])) - {"UNK"}
            promote = col_data.isin(["UNK"]) | col_data.isna()
            promote &= sp_data.isin(genus_vocab)
            col_data = col_data.where(~promote, other=sp_data)
        valid = set(categories.get(col, []))
        mapped = col_data.where(col_data.isin(valid), other="UNK")
        renamed[col] = pd.Categorical(mapped, categories=categories[col])

    return renamed[_MODEL_FEATURES]


# ---------------------------------------------------------------------------
# Source rank inference for model-inferred rows
# ---------------------------------------------------------------------------
def _infer_source_rank(row: pd.Series, categories: dict[str, list[str]]) -> str:
    # Genus names land in species_resolved (not genus) via NCBI lookup when
    # GBIF matches at genus rank. Check before iterating the standard ranks.
    sr = _ascii_normalize(row.get("species_resolved"))
    g = _ascii_normalize(row.get("genus"))
    if sr and sr != "UNK" and (not g or g == "UNK") and sr in set(categories.get("genus", [])):
        return "tbmML_genus"
    for rank in _RANK_ORDER:
        val = _ascii_normalize(row.get(rank))
        if val and val != "UNK" and val in set(categories.get(rank, [])):
            return f"tbmML_{rank}"
    return "tbmML_UNK"


def _unrepresented_mask(taxonomy_df: pd.DataFrame, categories: dict[str, list[str]]) -> list[bool]:
    """True for rows whose kingdom..genus share no value with the training vocabulary.

    Such rows would be scored on all-UNK features, which is a meaningless
    extrapolation, so predict_mass() returns NaN for them instead.  Uses the
    same rank inference as ``source``, so the test matches what the model sees
    (ASCII normalisation, GBIF kingdom remap, genus promotion).
    """
    return [
        _infer_source_rank(taxonomy_df.iloc[i], categories) == "tbmML_UNK"
        for i in range(len(taxonomy_df))
    ]


# ---------------------------------------------------------------------------
# Shared output assembler
# ---------------------------------------------------------------------------
def _assemble_output(
    log_preds: np.ndarray,
    taxonomy_df: pd.DataFrame,
    level: Optional[float],
    residuals: Optional[list[float]],
    input_names: list[str],
    include_taxonomy: bool,
    include_source: bool,
    interval_method: str = "pooled",
    by_rank_residuals: Optional[dict] = None,
) -> pd.DataFrame:
    """Convert log10 predictions to a result DataFrame with CI/taxonomy/source columns."""  # noqa: E501
    use_stratified = (
        level is not None
        and residuals is not None
        and len(residuals) > 0
        and interval_method == "stratified"
        and by_rank_residuals is not None
    )
    need_cats = include_source or use_stratified
    categories = load_categories() if need_cats else None

    q_pooled = (
        float(np.quantile(residuals, level))
        if (level is not None and residuals is not None and len(residuals) > 0)
        else None
    )

    rows = []
    for i, (name, log_pred) in enumerate(zip(input_names, log_preds)):
        row: dict = {"taxon": name, "mass_g": float(10**log_pred)}
        src = None
        if level is not None:
            if use_stratified:
                src = _infer_source_rank(taxonomy_df.iloc[i], categories)
                rank_key = src.replace("tbmML_", "")
                rank_res = by_rank_residuals.get(rank_key)
                if rank_res and len(rank_res) >= 10:
                    q_row = float(np.quantile(rank_res, level))
                else:
                    q_row = q_pooled
                row["lower_bound"] = (
                    float(10 ** (log_pred - q_row))
                    if q_row is not None
                    else float("nan")  # noqa: E501
                )
                row["upper_bound"] = (
                    float(10 ** (log_pred + q_row))
                    if q_row is not None
                    else float("nan")  # noqa: E501
                )
            else:
                row["lower_bound"] = (
                    float(10 ** (log_pred - q_pooled))
                    if q_pooled is not None
                    else float("nan")  # noqa: E501
                )
                row["upper_bound"] = (
                    float(10 ** (log_pred + q_pooled))
                    if q_pooled is not None
                    else float("nan")  # noqa: E501
                )
            row["confidence"] = level
        if include_taxonomy:
            for col in _TAXONOMY_INPUT_COLS:
                row[col] = (
                    taxonomy_df[col].iloc[i] if col in taxonomy_df.columns else None
                )  # noqa: E501
        if include_source:
            if src is None:
                src = _infer_source_rank(taxonomy_df.iloc[i], categories)
            row["source"] = src
        rows.append(row)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# XGBoost predictor
# ---------------------------------------------------------------------------
def _predict_xgboost(
    taxonomy_df: pd.DataFrame,
    level: Optional[float],
    include_taxonomy: bool,
    input_names: list[str],
    include_source: bool,
    interval_method: str = "pooled",
) -> pd.DataFrame:
    _ensure_artifacts()
    categories = load_categories()
    model = load_model()
    X = _apply_unk_mapping(taxonomy_df, categories)
    # The model was trained with native categorical splits on pd.Categorical
    # columns whose categories are exactly categories.json (UNK first, then
    # sorted).  Column order is taken from the model itself: xgboost does not
    # reorder by name, so a wrong order would silently mispredict.
    feature_names = model.feature_names
    if not feature_names:
        raise RuntimeError(
            "model.ubj carries no feature_names; cannot align input columns. "
            "Re-download the artifacts with download_model(force=True)."
        )
    dmat = xgb.DMatrix(X[feature_names], enable_categorical=True)
    log_preds = model.predict(dmat)
    residuals = load_calibration() if level is not None else None
    by_rank = (
        load_calibration_by_rank()
        if (level is not None and interval_method == "stratified")
        else None
    )
    return _assemble_output(
        log_preds,
        taxonomy_df,
        level,
        residuals,
        input_names,
        include_taxonomy,
        include_source,
        interval_method,
        by_rank,
    )


# ---------------------------------------------------------------------------
# Entity Embeddings predictor
# ---------------------------------------------------------------------------
_EE_DIMS = {
    "kingdom": 4,
    "phylum": 8,
    "class": 8,
    "order": 16,
    "family": 16,
    "genus": 32,
}
_EE_TOTAL_DIM = sum(_EE_DIMS.values())  # 84


def _predict_entity_embeddings(
    taxonomy_df: pd.DataFrame,
    level: Optional[float],
    include_taxonomy: bool,
    input_names: list[str],
    include_source: bool,
    interval_method: str = "pooled",
) -> pd.DataFrame:
    _ensure_artifacts()
    embeddings = load_embeddings()

    # Map each taxonomy value to its embedding; unseen values → UNK vector
    n = len(taxonomy_df)
    X = np.zeros((n, _EE_TOTAL_DIM), dtype=np.float32)
    offset = 0
    for col in _MODEL_FEATURES:
        dim = _EE_DIMS[col]
        col_embs = embeddings[col]
        unk_vec = np.array(col_embs["UNK"], dtype=np.float32)
        vals = (
            taxonomy_df[col].fillna("UNK") if col in taxonomy_df.columns else pd.Series(["UNK"] * n)
        )
        if col == "kingdom":
            # Apply GBIF v2 kingdom remapping (same as _apply_unk_mapping).
            normed = vals.apply(lambda x: _ascii_normalize(x) or "UNK")
            vals = normed.map(lambda x: _GBIF_KINGDOM_NORM.get(x, x))
        if col == "genus":
            sp_col = "species_resolved"
            sp_vals = (
                taxonomy_df[sp_col].fillna("UNK")
                if sp_col in taxonomy_df.columns
                else pd.Series(["UNK"] * n)
            )
            genus_vocab = set(col_embs.keys()) - {"UNK"}
            norm_g = vals.apply(lambda x: _ascii_normalize(x) or "UNK")
            norm_sp = sp_vals.apply(lambda x: _ascii_normalize(x) or "UNK")
            promote = (norm_g == "UNK") & norm_sp.isin(genus_vocab)
            if promote.any():
                vals = vals.copy()
                vals[promote] = sp_vals[promote]
        for i, val in enumerate(vals):
            norm = _ascii_normalize(val) or "UNK"
            X[i, offset : offset + dim] = col_embs.get(norm, unk_vec)
        offset += dim

    dmat = xgb.DMatrix(X)
    log_preds = load_model_ee().predict(dmat)
    residuals = load_calibration_ee() if level is not None else None
    by_rank = (
        load_calibration_by_rank_ee()
        if (level is not None and interval_method == "stratified")
        else None
    )
    return _assemble_output(
        log_preds,
        taxonomy_df,
        level,
        residuals,
        input_names,
        include_taxonomy,
        include_source,
        interval_method,
        by_rank,
    )


# ---------------------------------------------------------------------------
# Method dispatch table
# ---------------------------------------------------------------------------
_METHODS = {
    "XGBoost": _predict_xgboost,
    "EntityEmbeddings": _predict_entity_embeddings,
}


# ---------------------------------------------------------------------------
# Public: predict_mass()
# ---------------------------------------------------------------------------
def predict_mass(
    taxon,
    confidence_interval=False,
    method: str = "EntityEmbeddings",
    interval_method: str = "stratified",
    include_taxonomy: bool = False,
    fuzzy_match_name: bool = False,
    include_source: bool = False,
    lookup: bool = True,
) -> pd.DataFrame:
    """Predict body mass for one or more taxa.

    Parameters
    ----------
    taxon : str, list of str, or pd.DataFrame
        Scientific name(s) to predict.  Pass a ``pd.DataFrame`` with columns
        ``kingdom``, ``phylum``, ``class``, ``order``, ``family``, ``genus``,
        ``species_resolved`` to skip the taxonomy lookup step.
    confidence_interval : bool or float
        ``False`` — no interval (default).
        ``True`` — 90% conformal prediction interval.
        ``float`` in (0, 1) — interval at that coverage level.
        Conformal intervals apply only to model-inferred values; rows returned
        from the training-data dictionary receive ``NaN`` bounds.
    interval_method : str
        How the conformal half-width is computed when ``confidence_interval``
        is not ``False``.  ``"stratified"`` (default) uses rank-specific
        calibration residuals, providing approximate conditional coverage per
        taxonomic rank.  ``"pooled"`` applies a single quantile from all
        calibration residuals, providing the marginal conformal guarantee.
    method : str
        Prediction method.  ``"EntityEmbeddings"`` (default; two-stage:
        taxonomy embeddings + XGBoost on embedding vectors) or ``"XGBoost"``
        (direct XGBoost on natively categorical taxonomy features).
    include_taxonomy : bool
        If ``True``, include the resolved taxonomy columns in the output.
    fuzzy_match_name : bool
        If ``True``, species names are first corrected via the GBIF
        species-match API before taxonomy lookup, tolerating misspellings and
        minor name variants.  A ``matched_name`` column is appended to the
        output: it contains the originally entered name when a correction was
        applied or no GBIF match was found; ``None`` when the name was already
        canonical.  Default ``False`` (exact name matching).  Ignored when
        ``taxon`` is a ``pd.DataFrame``.
    include_source : bool
        If ``True``, append a ``source`` column identifying the provenance of
        each returned mass value.  For taxa returned directly from the
        training-data dictionary the value is the original source identifier
        (e.g., ``"fishbase"``, ``"Novak_unpubl"``).  For model-inferred
        values it is ``"tbmML_"`` followed by the finest taxonomic rank
        present in the training data (e.g., ``"tbmML_genus"`` if the genus
        was seen during training; ``"tbmML_order"`` if only the order was
        seen).  Taxa whose resolved taxonomy shares no rank with the training
        data receive ``"tbmML_UNK"``; unresolvable taxa receive ``None``.
        Default ``False``.
    lookup : bool
        If ``True`` (default), taxa found in the training-data dictionary are
        returned with their empirical mass and bypass the model.  If
        ``False``, every resolved taxon is passed through the model specified
        by ``method``.

    Returns
    -------
    pd.DataFrame
        Always includes ``taxon`` and ``mass_g`` (grams).
        With ``confidence_interval != False``: also ``lower_bound``,
        ``upper_bound``, ``confidence`` (``NaN`` for dictionary-sourced rows).
        With ``include_taxonomy=True``: also ``kingdom`` … ``species_resolved``.
        With ``fuzzy_match_name=True``: also ``matched_name`` (the originally
        entered name if corrected or unmatched; ``None`` if no correction was
        needed).
        With ``include_source=True``: also ``source``.
        Rows for unresolvable species, and rows whose resolved taxonomy shares
        no rank with the training data (a warning lists them), have ``NaN``
        for numeric columns.
    """
    if method not in _METHODS:
        raise ValueError(f"Unknown method {method!r}. Available: {list(_METHODS)}")
    interval_method = _resolve_interval_method(interval_method)
    level = _resolve_ci_level(confidence_interval)

    # ---- Input handling ------------------------------------------------
    if isinstance(taxon, pd.DataFrame):
        required = set(_TAXONOMY_INPUT_COLS)
        missing = required - set(taxon.columns)
        if missing:
            raise ValueError(
                f"Input DataFrame is missing taxonomy columns: {sorted(missing)}"
            )  # noqa: E501
        taxonomy_df = taxon.reset_index(drop=True)
        input_names = taxonomy_df.get(
            "species", taxonomy_df["species_resolved"]
        ).tolist()  # noqa: E501
        matched_names = None
    else:
        if isinstance(taxon, str):
            names = [taxon]
        else:
            names = list(taxon)
        if fuzzy_match_name:
            from ._fuzzy import fuzzy_lookup_taxonomy  # noqa: E501 local import avoids circular dep

            tax_full = fuzzy_lookup_taxonomy(names)
            corrected = tax_full["matched_name"].notna() & (
                tax_full["matched_name"] != tax_full["input_name"]
            )
            no_match = tax_full["matched_name"].isna()
            # Plain lists so "no value" stays None (pandas 3 would coerce to NaN).
            input_names = [
                m if c else (None if nm else i)
                for m, i, c, nm in zip(
                    tax_full["matched_name"], tax_full["input_name"], corrected, no_match
                )
            ]
            matched_names = [
                i if (c or nm) else None
                for i, c, nm in zip(tax_full["input_name"], corrected, no_match)
            ]
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
        if include_source:
            cols += ["source"]
        if matched_names is not None:
            cols += ["matched_name"]
        return pd.DataFrame(columns=cols)

    # ---- Rows with failed lookup (all None) get NaN predictions ----------
    resolved_mask = taxonomy_df["species_resolved"].notna()

    if not resolved_mask.any():
        warnings.warn(
            "No species could be resolved; returning all-NaN result.", stacklevel=2
        )  # noqa: E501

    resolved_pos = [i for i, ok in enumerate(resolved_mask) if ok]
    unresolved_pos = [i for i, ok in enumerate(resolved_mask) if not ok]

    result_rows = []

    if resolved_mask.any():
        sub = taxonomy_df[resolved_mask].reset_index(drop=True)
        sub_names = [input_names[i] for i in resolved_pos]

        # Download/verify the artifacts before any loader runs: the dictionary
        # lookup and the vocabulary check below read lookup.json and
        # categories.json ahead of the model functions (which ensure again,
        # cheaply).  Without this a fresh install failed with FileNotFoundError.
        _ensure_artifacts()

        # ---- Dictionary lookup (optional): return empirical mass for known species ---
        if lookup:
            lkp = load_lookup()
            hit_mask = sub["species_resolved"].isin(lkp)
            dict_indices = [i for i, h in enumerate(hit_mask) if h]
            model_indices = [i for i, h in enumerate(hit_mask) if not h]
        else:
            dict_indices = []
            model_indices = list(range(len(sub)))

        if dict_indices:
            dict_sub = sub.iloc[dict_indices].reset_index(drop=True)
            dict_names = [sub_names[i] for i in dict_indices]
            dict_data = []
            for i, (name, sp) in enumerate(
                zip(dict_names, dict_sub["species_resolved"])
            ):  # noqa: E501
                entry = lkp[sp]
                row: dict = {"taxon": name, "mass_g": float(entry["mass_g"])}
                if level is not None:
                    row["lower_bound"] = float("nan")
                    row["upper_bound"] = float("nan")
                    row["confidence"] = float("nan")
                if include_taxonomy:
                    for col in _TAXONOMY_INPUT_COLS:
                        row[col] = (
                            dict_sub[col].iloc[i] if col in dict_sub.columns else None
                        )  # noqa: E501
                if include_source:
                    row["source"] = entry["source"]
                dict_data.append(row)
            dict_df = pd.DataFrame(dict_data)
            dict_df["_orig_idx"] = [resolved_pos[i] for i in dict_indices]
            result_rows.append(dict_df)

        if model_indices:
            model_sub = sub.iloc[model_indices].reset_index(drop=True)
            model_names = [sub_names[i] for i in model_indices]

            # Taxa whose kingdom..genus share no value with the training
            # vocabulary would be scored on all-UNK features: return NaN for
            # them (with a warning), as for unresolvable names.
            unrep = _unrepresented_mask(model_sub, load_categories())
            unrep_pos = [i for i, u in enumerate(unrep) if u]
            keep_pos = [i for i, u in enumerate(unrep) if not u]

            if unrep_pos:
                unrep_names = [model_names[i] for i in unrep_pos]
                shown = ", ".join(repr(n) for n in unrep_names[:10])
                if len(unrep_names) > 10:
                    shown += f", ... ({len(unrep_names) - 10} more)"
                warnings.warn(
                    f"{len(unrep_names)} taxon/taxa resolved to a taxonomy with no rank "
                    f"present in the training data; returning NaN: {shown}",
                    stacklevel=2,
                )
                unrep_rows = []
                for i, name in zip(unrep_pos, unrep_names):
                    row = {"taxon": name, "mass_g": float("nan")}
                    if level is not None:
                        row.update(
                            {
                                "lower_bound": float("nan"),
                                "upper_bound": float("nan"),
                                "confidence": float("nan"),
                            }
                        )
                    if include_taxonomy:
                        for col in _TAXONOMY_INPUT_COLS:
                            row[col] = model_sub[col].iloc[i] if col in model_sub.columns else None
                    if include_source:
                        row["source"] = "tbmML_UNK"
                    unrep_rows.append(row)
                unrep_df = pd.DataFrame(unrep_rows)
                unrep_df["_orig_idx"] = [resolved_pos[model_indices[i]] for i in unrep_pos]
                result_rows.append(unrep_df)

            if keep_pos:
                keep_sub = model_sub.iloc[keep_pos].reset_index(drop=True)
                keep_names = [model_names[i] for i in keep_pos]
                good_df = _METHODS[method](
                    keep_sub,
                    level,
                    include_taxonomy,
                    keep_names,
                    include_source,
                    interval_method,
                )
                good_df["_orig_idx"] = [resolved_pos[model_indices[i]] for i in keep_pos]
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
                        "confidence": float("nan"),
                    }
                )
        if include_taxonomy:
            for r in nan_rows:
                r.update({c: None for c in _TAXONOMY_INPUT_COLS})
        if include_source:
            for r in nan_rows:
                r["source"] = None
        nan_df = pd.DataFrame(nan_rows)
        nan_df["_orig_idx"] = unresolved_pos
        result_rows.append(nan_df)

    out = pd.concat(result_rows, ignore_index=True)
    out = out.sort_values("_orig_idx").drop(columns="_orig_idx").reset_index(drop=True)

    if matched_names is not None:
        out["matched_name"] = matched_names

    return out
