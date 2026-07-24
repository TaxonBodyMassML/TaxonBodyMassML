"""
Taxonomy resolution: GBIF fuzzy match → NCBI Entrez fallback.

Includes session-level in-memory cache, optional persistent disk cache,
concurrent lookups via ThreadPoolExecutor, and optional tqdm progress bar.
"""

import os
import shelve
import threading
import warnings
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import pandas as pd

from ._http import _get

GBIF_MATCH_URL = "https://api.gbif.org/v2/species/match"
NCBI_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
NCBI_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

# ---------------------------------------------------------------------------
# tqdm (optional dependency)
# ---------------------------------------------------------------------------
try:
    from tqdm import tqdm as _tqdm

    _have_tqdm = True
except ImportError:
    _tqdm = None
    _have_tqdm = False

# ---------------------------------------------------------------------------
# Session cache
# ---------------------------------------------------------------------------
_SESSION_CACHE: dict[str, dict] = {}
_DISK_CACHE_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# Options (set via tbm_options())
# ---------------------------------------------------------------------------
_OPTIONS: dict = {
    "disk_cache": False,
    "progress": True,
}


def tbm_options(**kwargs) -> None:
    """Configure package-level options.

    Parameters
    ----------
    disk_cache : bool
        Persist resolved taxonomy to disk across Python sessions.
    progress : bool
        Show a tqdm progress bar when looking up more than 10 species.
    """
    for k, v in kwargs.items():
        if k not in _OPTIONS:
            raise ValueError(f"Unknown option: {k!r}")
        _OPTIONS[k] = v


def tbm_clear_cache(disk: bool = True, session: bool = True) -> None:
    """Clear the in-memory and/or on-disk taxonomy cache."""
    global _SESSION_CACHE
    if session:
        _SESSION_CACHE = {}
    if disk:
        with _DISK_CACHE_LOCK:
            with _open_disk_cache() as db:
                db.clear()


# ---------------------------------------------------------------------------
# Disk cache helpers
# ---------------------------------------------------------------------------
def _cache_db_path() -> str:
    try:
        from platformdirs import user_cache_dir

        base = user_cache_dir("TaxonBodyMassML")
    except ImportError:
        import pathlib

        base = str(pathlib.Path.home() / ".cache" / "TaxonBodyMassML")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "taxonomy_cache")


def _open_disk_cache() -> shelve.Shelf:
    return shelve.open(_cache_db_path(), flag="c", writeback=False)


# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------
def _normalise(name: str) -> str:
    return name.strip().lower().replace("_", " ")


# ---------------------------------------------------------------------------
# GBIF lookup
# ---------------------------------------------------------------------------
def _gbif_lookup(name: str) -> dict:
    resp = _get(GBIF_MATCH_URL, {"scientificName": name})
    if resp.status_code != 200:
        return {}
    data = resp.json()
    return {field: data.get(field) for field in TAXONOMY_COLS}


# ---------------------------------------------------------------------------
# NCBI lookup
# ---------------------------------------------------------------------------
def _ncbi_lookup(name: str) -> dict:
    resp = _get(
        NCBI_ESEARCH,
        {"db": "taxonomy", "term": name, "retmode": "json"},
        ncbi=True,
    )
    if resp.status_code != 200:
        return {}
    ids = resp.json().get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {}

    resp2 = _get(
        NCBI_EFETCH,
        {"db": "taxonomy", "id": ids[0], "retmode": "xml"},
        ncbi=True,
    )
    if resp2.status_code != 200:
        return {}

    return _parse_ncbi_xml(resp2.text)


def _parse_ncbi_xml(xml_text: str) -> dict:
    taxons: dict = {}
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return taxons
    lineage = root.find(".//LineageEx")
    if lineage is not None:
        for taxon in lineage.findall("Taxon"):
            rank_el = taxon.find("Rank")
            name_el = taxon.find("ScientificName")
            if rank_el is None or name_el is None:
                continue
            if rank_el.text is None:
                continue
            taxons[rank_el.text.lower()] = name_el.text
    sp = root.find(".//ScientificName")
    if sp is not None:
        taxons["species"] = sp.text
    return taxons


# ---------------------------------------------------------------------------
# Single-species resolution (with caching)
# ---------------------------------------------------------------------------
def _resolve_one(name: str) -> Optional[dict]:
    """Return a 7-rank taxonomy dict for *name*, or None if unresolvable."""
    key = _normalise(name)

    if key in _SESSION_CACHE:
        return _SESSION_CACHE[key]

    if _OPTIONS["disk_cache"]:
        with _DISK_CACHE_LOCK:
            with _open_disk_cache() as db:
                if key in db:
                    result = db[key]
                    _SESSION_CACHE[key] = result
                    return result

    taxonomy = _gbif_lookup(name)

    if not taxonomy or any(v is None for v in taxonomy.values()):
        ncbi = _ncbi_lookup(name)
        for field in TAXONOMY_COLS:
            if taxonomy.get(field) is None:
                taxonomy[field] = ncbi.get(field)

    taxonomy = {f: taxonomy.get(f) or "UNK" for f in TAXONOMY_COLS}

    if all(v == "UNK" for v in taxonomy.values()):
        return None

    _SESSION_CACHE[key] = taxonomy
    if _OPTIONS["disk_cache"]:
        with _DISK_CACHE_LOCK:
            with _open_disk_cache() as db:
                db[key] = taxonomy

    return taxonomy


# ---------------------------------------------------------------------------
# Public: lookup_taxonomy()
# ---------------------------------------------------------------------------
def lookup_taxonomy(species) -> pd.DataFrame:
    """Resolve scientific names to 7-rank taxonomy.

    Parameters
    ----------
    species : str or list of str
        One or more species names (scientific).

    Returns
    -------
    pd.DataFrame
        Columns: ``species`` (input name), ``kingdom``, ``phylum``,
        ``class``, ``order``, ``family``, ``genus``, ``species_resolved``.
        Rows with unresolvable names emit a warning and contain ``NaN``.
    """
    if isinstance(species, str):
        names = [species]
    else:
        names = list(species)

    results: dict[str, Optional[dict]] = {}

    # Progress bar (opt-in; tqdm is a Suggests dep)
    show_progress = (
        _OPTIONS["progress"]
        and len(names) > 10
        and not os.environ.get("TAXONBODYMASSML_PROGRESS", "1") == "0"
    )

    workers = min(len(names), 8) if len(names) > 1 else 1

    if workers == 1:
        iter_names = (
            _tqdm(names, desc="Resolving taxonomy") if (show_progress and _have_tqdm) else names
        )
        for n in iter_names:
            results[n] = _resolve_one(n)
    else:
        futures = {}
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for n in names:
                futures[pool.submit(_resolve_one, n)] = n
            done_iter = as_completed(futures)
            if show_progress and _have_tqdm:
                done_iter = _tqdm(done_iter, total=len(futures), desc="Resolving taxonomy")
            for fut in done_iter:
                n = futures[fut]
                try:
                    results[n] = fut.result()
                except Exception:
                    results[n] = None  # treated as unresolvable; warning below

    # Build output DataFrame
    rows = []
    unresolvable = []
    for n in names:
        tax = results.get(n)
        if tax is None:
            unresolvable.append(n)
            rows.append(
                {
                    "species": n,
                    **{c: None for c in TAXONOMY_COLS[:-1]},
                    "species_resolved": None,
                }
            )
        else:
            rows.append(
                {
                    "species": n,
                    "kingdom": tax["kingdom"],
                    "phylum": tax["phylum"],
                    "class": tax["class"],
                    "order": tax["order"],
                    "family": tax["family"],
                    "genus": tax["genus"],
                    "species_resolved": tax["species"],
                }
            )

    if unresolvable:
        warnings.warn(
            f"Could not resolve taxonomy for: {', '.join(repr(s) for s in unresolvable)}. "
            "Predictions for these species will be NaN.",
            stacklevel=3,
        )

    return pd.DataFrame(rows)
