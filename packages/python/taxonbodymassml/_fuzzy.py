"""Fuzzy species-name matching via GBIF.

These functions wrap the existing strict taxonomy functions with a GBIF
fuzzy-matching pre-pass.  The underlying ``lookup_taxonomy()`` and
``predict_mass()`` functions assume species names are correctly spelled;
call these variants when names may be misspelled or non-canonical.
"""

import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd

from ._http import _get
from ._lookup import GBIF_MATCH_URL, lookup_taxonomy

_MATCH_ACCEPTED = {"EXACT", "FUZZY"}


# ---------------------------------------------------------------------------
# Internal: GBIF canonical name for one species
# ---------------------------------------------------------------------------

def _gbif_fuzzy_name(name: str) -> Optional[str]:
    """Return GBIF's canonical species name for *name*, or None."""
    try:
        resp = _get(GBIF_MATCH_URL, {"scientificName": name})
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get("matchType") not in _MATCH_ACCEPTED:
            return None
        matched = data.get("species")
        return str(matched) if matched else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public: correct_species_names()
# ---------------------------------------------------------------------------

def correct_species_names(species) -> pd.DataFrame:
    """Suggest corrected species names via GBIF fuzzy matching.

    Queries the GBIF species-match endpoint for each name and returns the
    canonical matched name.  Use this to inspect potential corrections before
    passing names to ``lookup_taxonomy()`` or ``predict_mass()``.

    Parameters
    ----------
    species : str or list of str
        One or more species names (possibly misspelled).

    Returns
    -------
    pd.DataFrame
        Columns: ``input_name`` (the original string) and ``matched_name``
        (GBIF's canonical name, or ``None`` when no match was found).
    """
    if isinstance(species, str):
        names = [species]
    else:
        names = list(species)

    workers = min(len(names), 8) if len(names) > 1 else 1
    matched: dict[str, Optional[str]] = {}

    if workers == 1:
        for n in names:
            matched[n] = _gbif_fuzzy_name(n)
    else:
        futures = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for n in names:
                futures[pool.submit(_gbif_fuzzy_name, n)] = n
            for fut in as_completed(futures):
                n = futures[fut]
                try:
                    matched[n] = fut.result()
                except Exception:
                    matched[n] = None

    return pd.DataFrame({
        "input_name": names,
        "matched_name": [matched[n] for n in names],
    })


# ---------------------------------------------------------------------------
# Public: fuzzy_lookup_taxonomy()
# ---------------------------------------------------------------------------

def fuzzy_lookup_taxonomy(species) -> pd.DataFrame:
    """Look up taxonomy for potentially misspelled species names.

    Runs ``correct_species_names()`` first to obtain GBIF-canonical names,
    then calls ``lookup_taxonomy()`` with the corrected names.  A warning is
    issued listing any names that were auto-corrected.

    Parameters
    ----------
    species : str or list of str
        One or more species names (possibly misspelled).

    Returns
    -------
    pd.DataFrame
        Same columns as ``lookup_taxonomy()``, plus ``input_name`` and
        ``matched_name`` prepended.
    """
    corrections = correct_species_names(species)

    # Use matched_name where GBIF found one; fall back to input_name
    lookup_names = corrections["matched_name"].where(
        corrections["matched_name"].notna(), corrections["input_name"]
    ).tolist()

    changed = corrections["matched_name"].notna() & (
        corrections["matched_name"] != corrections["input_name"]
    )
    if changed.any():
        pairs = "; ".join(
            f"{r.input_name!r} -> {r.matched_name!r}"
            for r in corrections[changed].itertuples()
        )
        warnings.warn(
            f"Fuzzy-matched {changed.sum()} name(s): {pairs}",
            stacklevel=2,
        )

    tax_df = lookup_taxonomy(lookup_names)
    tax_df.insert(0, "input_name", corrections["input_name"].tolist())
    tax_df.insert(1, "matched_name", corrections["matched_name"].tolist())
    return tax_df


# ---------------------------------------------------------------------------
# Public: fuzzy_predict_mass()
# ---------------------------------------------------------------------------

def fuzzy_predict_mass(species, **kwargs) -> pd.DataFrame:
    """Predict body mass for potentially misspelled species names.

    Runs ``correct_species_names()`` to obtain GBIF-canonical names, then
    calls ``predict_mass()`` with the corrected names.  The output ``species``
    column contains the original input names; a ``matched_name`` column is
    appended showing the corrected name (or ``None`` when no correction was
    found).

    Parameters
    ----------
    species : str or list of str
        Scientific name(s), possibly misspelled.
    **kwargs
        Passed through to ``predict_mass()``.

    Returns
    -------
    pd.DataFrame
        Same columns as ``predict_mass()`` with ``matched_name`` appended
        and ``species`` reflecting the original input names.
    """
    from ._predict import predict_mass  # local import avoids circular dependency

    tax_df = fuzzy_lookup_taxonomy(species)
    input_names = tax_df["input_name"].tolist()
    matched_names = tax_df["matched_name"].tolist()

    # Pass only the predict_mass-compatible columns (drop fuzzy extras)
    pred_input = tax_df.drop(columns=["input_name", "matched_name"])
    pred = predict_mass(pred_input, **kwargs)

    pred["species"] = input_names
    pred["matched_name"] = matched_names
    return pred
