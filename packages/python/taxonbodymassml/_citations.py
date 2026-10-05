"""
Bibliography helpers: the bundled data-source BibTeX file, the primary-source
bibliography and provenance table (artifacts), and per-result .bib export.
"""

from __future__ import annotations

import re
import unicodedata
import warnings
from pathlib import Path

import pandas as pd

_DATA_DIR = Path(__file__).parent / "data"

# Model-inferred rows carry "tbmML_<rank>" in the source column (matched
# case-insensitively; the shorter "tbml_" spelling is accepted too).
_MODEL_MARKER = re.compile(r"^tbm_?ml_|^tbml_", re.IGNORECASE)
# Unicode hyphens/dashes (U+2010..U+2015) and the minus sign (U+2212).
_DASHES = re.compile("[‐‑‒–—―−]")
# Characters that never occur in a real label but that transliteration can leave behind.
_STRAY = re.compile(r"[?'`^~\"]")
# Letters without a canonical decomposition that would otherwise be dropped.
_SPECIAL = str.maketrans(
    {
        "ı": "i",
        "ø": "o",
        "Ø": "O",
        "ß": "ss",
        "æ": "ae",
        "Æ": "AE",
        "œ": "oe",
        "Œ": "OE",
        "ł": "l",
        "Ł": "L",
        "đ": "d",
        "Đ": "D",
        "ð": "d",
        "Ð": "D",
        "þ": "th",
        "Þ": "Th",
    }
)
_NEXT_ENTRY = re.compile(r"^@", re.MULTILINE)

# Citation levels: the compilation a value was copied from ("source"), the
# study that measured the animal ("primary"), or both ("all").
_LEVELS = ("source", "primary", "all")
# Provenance artifacts (TaxonBodyMass_DB issue #1), distributed next to lookup.json.
_PRIMARY_BIB_FILE = "PrimaryCitations_BodyMass.bib"
_PROVENANCE_FILE = "TaxonBodyMass_Provenance.csv.gz"
# match_status values of a verified primary reference.  Conversion-factor rows
# (provenance_type == "conversion_factor") carry no status and are always cited.
_ACCEPTED_STATUS = frozenset({"certain", "approved", "nodoi_approved"})
_CONVERSION_TYPE = "conversion_factor"
_PROVENANCE_COLS = [
    "genus",
    "species",
    "taxon",
    "source_mass",
    "source_bibcite",
    "origin",
    "hop",
    "via_cite_id",
    "ref_role",
    "provenance_type",
    "primary_cite_id",
    "primary_bibcite",
    "primary_doi",
    "match_status",
    "n_records",
]


def get_citations(level: str = "source") -> Path | tuple[Path, Path]:
    """Return the path(s) to the TaxonBodyMassML bibliographies.

    Parameters
    ----------
    level : {"source", "primary", "all"}
        ``"source"`` (default): the bundled ``Citations_BodyMass.bib``, which
        lists every data source (compilation, database or primary study) whose
        body masses were used to train the model.  ``"primary"``: the
        generated ``PrimaryCitations_BodyMass.bib`` of verified primary
        references (the studies that measured the animals the compilations
        reproduce; TaxonBodyMass_DB issue #1).  It is a model artifact, fetched
        from Hugging Face on first use (like ``lookup.json``) and verified
        against a bundled checksum.  ``"all"``: both paths as a tuple
        ``(source, primary)``.

    Pass a path to ``bibtexparser.load()`` or open it in any reference manager
    (Zotero, BibDesk, JabRef, etc.).  See :func:`create_bib` to export only the
    references behind a particular set of predictions.

    Returns
    -------
    pathlib.Path or tuple of pathlib.Path
        Absolute path to the requested bibliography, or ``(source, primary)``
        for ``level="all"``.

    Raises
    ------
    ValueError
        If ``level`` is not one of ``"source"``, ``"primary"``, ``"all"``.
    RuntimeError
        For ``"primary"`` / ``"all"`` when the provenance artifacts cannot be
        obtained (no network, or an artifact revision that predates them).
    """
    level = _check_level(level)
    if level == "source":
        return _DATA_DIR / "Citations_BodyMass.bib"
    if level == "primary":
        return _primary_bib_path()
    return (_DATA_DIR / "Citations_BodyMass.bib", _primary_bib_path())


def create_bib(
    x: pd.DataFrame,
    file: str | Path = "TaxonBodyMass_sources.bib",
    level: str = "source",
) -> Path:
    """Write a BibTeX file of the references behind a set of predictions.

    Takes the output of :func:`predict_mass` called with ``include_source=True``
    and writes a ``.bib`` file with the BibTeX entries that the dictionary
    (training-data) rows of the result rest on, so users can cite exactly the
    empirical body-mass sources that contributed to their results.

    ``level="source"`` (default) cites the data sources named in the
    ``source`` column: each value is split on ``";"`` (a taxon recorded by
    several sources has a value such as ``"Feldman_etal_2016; Meiri_2018"``),
    trimmed and de-duplicated; model-inferred rows (``"tbmML_..."``) and
    missing values are ignored, so an output with no dictionary hits yields a
    bibliography with no entries.  Labels are matched to BibTeX keys through
    the bundled ``TaxonBodyMass_CitationCiteIDs.csv`` (compared after
    normalising whitespace, Unicode dashes and diacritics to plain ASCII) and
    the entries are copied verbatim from ``get_citations()``.

    ``level="primary"`` cites the studies that measured the animals: the
    dictionary species of ``x`` are joined to the provenance table
    (``TaxonBodyMass_Provenance.csv.gz``, a model artifact downloaded on first
    use) and every verified primary reference (``match_status`` ``certain``,
    ``approved`` or ``nodoi_approved``) and every conversion-factor reference
    of those species is written, taken from the primary bibliography or, for
    references that are themselves data sources, from the compilation
    bibliography.  The join uses the ``source_taxon`` column (the dictionary
    key; present when ``predict_mass`` was called with ``include_source=True``),
    falling back to ``species_resolved`` and then, with a warning, to
    ``taxon``.  Coverage is partial while TaxonBodyMass_DB ingests the
    sources' reference lists: species whose sources cite references that are
    not yet resolved are reported in a warning, so cite ``level="source"`` for
    them as well.

    ``level="all"`` writes the union of both levels without duplicate keys.
    The header line reports the number of entries per level.

    Parameters
    ----------
    x : pd.DataFrame
        A frame with a ``source`` column, as returned by
        ``predict_mass(..., include_source=True)``.
    file : str or pathlib.Path
        Path of the ``.bib`` file to write.  Default
        ``"TaxonBodyMass_sources.bib"`` in the working directory.  An existing
        file is overwritten.
    level : {"source", "primary", "all"}
        Which references to write (see above).

    Returns
    -------
    pathlib.Path
        Absolute path to the written file.

    Warns
    -----
    UserWarning
        If a source label has no citation mapping (it is skipped); if a mapped
        BibTeX key is missing from the bibliographies; for ``"primary"`` /
        ``"all"``, if dictionary species are absent from the provenance table,
        if their sources cite references that are not yet resolved, or if the
        join had to fall back to the ``taxon`` column.

    Raises
    ------
    ValueError
        If ``x`` is not a DataFrame with a ``source`` column, or ``level`` is
        invalid.

    Examples
    --------
    >>> import taxonbodymassml as tbm
    >>> res = tbm.predict_mass(["Nucella ostrina", "Anolis carolinensis"],
    ...                        include_source=True)  # doctest: +SKIP
    >>> tbm.create_bib(res, "my_sources.bib")  # doctest: +SKIP
    >>> tbm.create_bib(res, "my_primary_sources.bib", level="all")  # doctest: +SKIP
    """
    if not isinstance(x, pd.DataFrame) or "source" not in x.columns:
        raise ValueError(
            "`x` must be a DataFrame with a 'source' column; "
            "call predict_mass(..., include_source=True)."
        )
    level = _check_level(level)

    source_keys: list[str] = []
    primary_keys: list[str] = []
    if level in ("source", "all"):
        source_keys = _source_keys(x)
    if level in ("primary", "all"):
        primary_keys = _primary_keys(x)

    source_bib = get_citations("source").read_text(encoding="utf-8")
    primary_bib = (
        _primary_bib_path().read_text(encoding="utf-8") if level != "source" else ""
    )  # noqa: E501

    # Source entries come from the compilation bibliography; primary entries
    # from the primary bibliography, or from the compilation bibliography when
    # the primary reference is itself a data source (a shared key).
    written: set[str] = set()
    entries: list[str] = []
    missing: list[str] = []
    n_source = n_primary = 0
    for key in sorted(set(source_keys)):
        entry = _extract_bib_entry(source_bib, key)
        if entry is None:
            missing.append(key)
            continue
        entries.append(entry)
        written.add(key)
        n_source += 1
    for key in sorted(set(primary_keys)):
        entry = _extract_bib_entry(primary_bib, key) or _extract_bib_entry(source_bib, key)
        if entry is None:
            missing.append(key)
            continue
        n_primary += 1
        if key in written:
            continue
        entries.append(entry)
        written.add(key)
    if missing:
        warnings.warn(
            "BibTeX key(s) referenced by the citation tables but absent from the "
            "bibliographies: " + ", ".join(sorted(set(missing))),
            UserWarning,
            stacklevel=2,
        )

    if level == "source":
        counts = f"{n_source} data-source citation(s)"
    elif level == "primary":
        counts = f"{n_primary} primary-reference citation(s)"
    else:
        counts = (
            f"{n_source} data-source and {n_primary} primary-reference citation(s) "
            f"({len(entries)} unique)"
        )
    header = f"%% TaxonBodyMassML create_bib(): {counts} for {len(x)} taxa"
    body = "\n\n".join(entries)
    path = Path(file)
    path.write_text(header + "\n\n" + body + ("\n" if body else ""), encoding="utf-8")
    return path.resolve()


def _check_level(level) -> str:
    if not isinstance(level, str) or level not in _LEVELS:
        raise ValueError(
            f"`level` must be one of {', '.join(repr(lv) for lv in _LEVELS)}; got {level!r}."
        )
    return level


def _source_keys(x: pd.DataFrame) -> list[str]:
    """BibTeX keys of the data sources named in the ``source`` column."""
    tokens = _split_sources(x["source"])
    mapping = _read_citeids()
    keys: list[str] = []
    unmapped: list[str] = []
    for tok in tokens:
        bibcite = mapping.get(_normalise_label(tok))
        if bibcite is None:
            unmapped.append(tok)
        else:
            keys.append(bibcite)
    if unmapped:
        warnings.warn(
            f"{len(unmapped)} source label(s) have no citation mapping and were skipped: "
            + ", ".join(sorted(unmapped)),
            UserWarning,
            stacklevel=3,
        )
    return keys


def _dictionary_species(x: pd.DataFrame) -> list[str]:
    """Lookup keys of the dictionary rows of ``x`` (unique, first-seen order).

    For each dictionary row the key is ``source_taxon`` (the name under which
    the species was found in the training-data dictionary), falling back to
    ``species_resolved`` when that is missing and then to ``taxon`` (the input
    name, which may differ from the dictionary key; a warning is issued once
    when any row needs this last fallback).  Model-inferred and unresolved
    rows (``source`` ``tbmML_...`` or missing) are skipped.
    """

    def _present(v) -> bool:
        return (
            v is not None and not (not isinstance(v, str) and pd.isna(v)) and str(v).strip() != ""
        )

    is_dict = x["source"].map(
        lambda v: isinstance(v, str) and bool(v.strip()) and not _MODEL_MARKER.match(v.strip())
    )
    columns = [c for c in ("source_taxon", "species_resolved", "taxon") if c in x.columns]
    seen: set[str] = set()
    out: list[str] = []
    used_taxon = False
    for i, ok in enumerate(is_dict):
        if not ok:
            continue
        name = None
        for col in columns:
            v = x[col].iloc[i]
            if _present(v):
                name = str(v).strip()
                used_taxon = used_taxon or col == "taxon"
                break
        if name is not None and name not in seen:
            seen.add(name)
            out.append(name)
    if used_taxon:
        warnings.warn(
            "Some dictionary rows of `x` have no `source_taxon` or `species_resolved` value; "
            "joining the provenance table on `taxon` (input names) for them, which may differ "
            "from the dictionary keys. Call predict_mass(..., include_source=True) with this "
            "package version to get `source_taxon`.",
            UserWarning,
            stacklevel=4,
        )
    return out


def _primary_keys(x: pd.DataFrame) -> list[str]:
    """BibTeX keys of the verified primary (and conversion) references of the
    dictionary species of ``x``, from the provenance table."""
    species = _dictionary_species(x)
    if not species:
        return []
    prov = _read_provenance()
    rows = prov[prov["species"].isin(species)]

    absent = sorted(set(species) - set(rows["species"]))
    if absent:
        shown = ", ".join(absent[:10]) + (
            f", ... ({len(absent) - 10} more)" if len(absent) > 10 else ""
        )
        warnings.warn(
            f"{len(absent)} dictionary species absent from the provenance table (the "
            f"table may predate the species dictionary): {shown}",
            UserWarning,
            stacklevel=3,
        )

    accepted = rows["match_status"].isin(_ACCEPTED_STATUS) | (
        rows["provenance_type"] == _CONVERSION_TYPE
    )
    cited = rows[accepted & rows["primary_bibcite"].notna()]

    # Rows whose source cites a reference (hop >= 1) that is not (yet) verified:
    # the primary bibliography is incomplete for these species.
    unresolved = rows[(rows["hop"] >= 1) & ~rows["match_status"].isin(_ACCEPTED_STATUS)]
    if len(unresolved):
        n_sp = unresolved["species"].nunique()
        status = unresolved["match_status"].fillna("none").value_counts()
        status_txt = ", ".join(f"{k}: {v}" for k, v in status.items())
        warnings.warn(
            f"{n_sp} of {len(species)} dictionary species have source records whose primary "
            f"reference is not yet resolved ({len(unresolved)} record link(s); match_status "
            f"{status_txt}); cite these at level='source'.",
            UserWarning,
            stacklevel=3,
        )
    return cited["primary_bibcite"].tolist()


def _primary_bib_path() -> Path:
    """Path to the primary-source bibliography artifact (downloaded on first use)."""
    from ._model import provenance_path

    return provenance_path(_PRIMARY_BIB_FILE)


def _provenance_path() -> Path:
    """Path to the provenance table artifact (downloaded on first use)."""
    from ._model import provenance_path

    return provenance_path(_PROVENANCE_FILE)


def _read_provenance(path: Path | None = None) -> pd.DataFrame:
    """Read ``TaxonBodyMass_Provenance.csv.gz`` (TaxonBodyMass_DB pipeline step 7).

    One row per species x source label x reference.  All columns are read as
    strings (``NA`` -> missing) except ``hop`` and ``n_records`` (integers).
    """
    df = pd.read_csv(
        path or _provenance_path(),
        dtype=str,
        keep_default_na=False,
        na_values=["NA"],
        encoding="utf-8",
        compression="gzip",
    )
    missing = [c for c in _PROVENANCE_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"Provenance table is missing column(s): {', '.join(missing)}")
    df["hop"] = pd.to_numeric(df["hop"], errors="coerce").fillna(0).astype(int)
    df["n_records"] = pd.to_numeric(df["n_records"], errors="coerce").fillna(0).astype(int)
    return df


def _citeid_path() -> Path:
    """Path to the bundled CiteID -> BibTeX-key mapping."""
    return _DATA_DIR / "TaxonBodyMass_CitationCiteIDs.csv"


def _normalise_label(label) -> str:
    """Normalise a source label (or CiteID) to plain ASCII.

    Mirrors ``NormaliseSourceLabel()`` in TaxonBodyMass_DB: trims whitespace,
    converts non-breaking spaces, maps Unicode dashes to ``-`` and strips
    diacritics (``Cervigón`` -> ``Cervigon``) so hand-typed variants compare
    equal.
    """
    s = str(label).replace(" ", " ")
    s = _DASHES.sub("-", s)
    s = s.translate(_SPECIAL)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.encode("ascii", "ignore").decode("ascii")
    s = _STRAY.sub("", s)
    return s.strip()


def _split_sources(values) -> list[str]:
    """Unique dictionary labels from a ``source`` column, in first-seen order.

    Splits on ``;`` only (labels themselves contain ``_`` and ``-``), trims,
    drops missing/empty values and model-inferred ``tbmML_<rank>`` markers.
    """
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value is None or (not isinstance(value, str) and pd.isna(value)):
            continue
        for tok in str(value).split(";"):
            tok = tok.strip()
            if not tok or _MODEL_MARKER.match(tok) or tok in seen:
                continue
            seen.add(tok)
            out.append(tok)
    return out


def _read_citeids(path: Path | None = None) -> dict[str, str]:
    """Read the CiteID CSV into ``{normalised CiteID: Bibcite}``.

    Rows with an empty or ``NA`` CiteID are dropped.  Several CiteIDs may map
    to the same key (e.g. ``fishbase`` and ``Froese_2025``); the first
    occurrence of a normalised CiteID wins.
    """
    df = pd.read_csv(path or _citeid_path(), dtype=str, keep_default_na=False, encoding="utf-8")
    mapping: dict[str, str] = {}
    for bibcite, citeid in zip(df["Bibcite"], df["CiteID"]):
        key = _normalise_label(citeid)
        if key and key != "NA" and bibcite and key not in mapping:
            mapping[key] = bibcite
    return mapping


def _extract_bib_entry(bibtext: str, key: str) -> str | None:
    """Return the verbatim text of one BibTeX entry, or ``None`` if absent.

    The bundled bibliography is a BibDesk export: every entry starts at column
    0 with ``@type{Key,`` and there are no ``@string``/``@preamble``/``@comment``
    blocks, so an entry runs from its ``@`` line to the line before the next
    ``@`` line (or EOF).  The trailing ``,`` after the key prevents
    ``Meiri:2018a`` matching ``Meiri:2018aa``.
    """
    start = re.search(r"^@[A-Za-z]+\{" + re.escape(key) + ",", bibtext, re.MULTILINE)
    if start is None:
        return None
    nxt = _NEXT_ENTRY.search(bibtext, start.end())
    end = nxt.start() if nxt else len(bibtext)
    return bibtext[start.start() : end].rstrip()
