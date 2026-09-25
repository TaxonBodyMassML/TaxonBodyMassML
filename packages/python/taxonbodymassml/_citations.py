"""
Bibliography helpers: the bundled data-source BibTeX file and per-result .bib export.
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


def get_citations() -> Path:
    """Return the path to the bundled Citations_BodyMass.bib file.

    The BibTeX file lists all data sources used to train the TaxonBodyMassML
    model.  Pass the path to ``bibtexparser.load()`` or open it in any
    reference manager (Zotero, BibDesk, JabRef, etc.).  See :func:`create_bib`
    to export only the sources cited by a particular set of predictions.

    Returns
    -------
    pathlib.Path
        Absolute path to ``taxonbodymassml/data/Citations_BodyMass.bib``.
    """
    return _DATA_DIR / "Citations_BodyMass.bib"


def create_bib(x: pd.DataFrame, file: str | Path = "TaxonBodyMass_sources.bib") -> Path:
    """Write a BibTeX file of the data sources behind a set of predictions.

    Takes the output of :func:`predict_mass` called with ``include_source=True``
    and writes a ``.bib`` file containing the BibTeX entries for every
    training-data source cited in its ``source`` column, so users can cite
    exactly the empirical body-mass sources that contributed to their results.

    Each ``source`` value is split on ``";"`` (a taxon recorded by several
    sources has a value such as ``"Feldman_etal_2016; Meiri_2018"``), trimmed
    and de-duplicated.  Model-inferred rows, whose ``source`` begins with
    ``"tbmML_"``, and missing values are ignored, so an output with no
    dictionary hits yields a bibliography with no entries.

    Source labels are matched to BibTeX keys through the bundled
    ``TaxonBodyMass_CitationCiteIDs.csv`` and the entries are copied verbatim
    from the file returned by :func:`get_citations`.  Labels and keys are
    compared after normalising whitespace, Unicode dashes and diacritics to
    plain ASCII, so minor typographic variants still match.

    Parameters
    ----------
    x : pd.DataFrame
        A frame with a ``source`` column, as returned by
        ``predict_mass(..., include_source=True)``.
    file : str or pathlib.Path
        Path of the ``.bib`` file to write.  Default
        ``"TaxonBodyMass_sources.bib"`` in the working directory.  An existing
        file is overwritten.

    Returns
    -------
    pathlib.Path
        Absolute path to the written file.

    Warns
    -----
    UserWarning
        If any source label has no citation mapping (it is skipped), or if a
        mapped BibTeX key is missing from the bundled bibliography.

    Raises
    ------
    ValueError
        If ``x`` is not a DataFrame with a ``source`` column.

    Examples
    --------
    >>> import taxonbodymassml as tbm
    >>> res = tbm.predict_mass(["Nucella ostrina", "Anolis carolinensis"],
    ...                        include_source=True)  # doctest: +SKIP
    >>> tbm.create_bib(res, "my_sources.bib")  # doctest: +SKIP
    """
    if not isinstance(x, pd.DataFrame) or "source" not in x.columns:
        raise ValueError(
            "`x` must be a DataFrame with a 'source' column; "
            "call predict_mass(..., include_source=True)."
        )

    tokens = _split_sources(x["source"])
    mapping = _read_citeids()

    keys: set[str] = set()
    unmapped: list[str] = []
    for tok in tokens:
        bibcite = mapping.get(_normalise_label(tok))
        if bibcite is None:
            unmapped.append(tok)
        else:
            keys.add(bibcite)
    if unmapped:
        warnings.warn(
            f"{len(unmapped)} source label(s) have no citation mapping and were skipped: "
            + ", ".join(sorted(unmapped)),
            UserWarning,
            stacklevel=2,
        )

    bibtext = get_citations().read_text(encoding="utf-8")
    entries: list[str] = []
    missing: list[str] = []
    for key in sorted(keys):
        entry = _extract_bib_entry(bibtext, key)
        if entry is None:
            missing.append(key)
        else:
            entries.append(entry)
    if missing:
        warnings.warn(
            "BibTeX key(s) listed in TaxonBodyMass_CitationCiteIDs.csv but absent from "
            "Citations_BodyMass.bib: " + ", ".join(missing),
            UserWarning,
            stacklevel=2,
        )

    header = (
        f"%% TaxonBodyMassML create_bib(): {len(entries)} data-source citation(s) "
        f"for {len(x)} taxa"
    )
    body = "\n\n".join(entries)
    path = Path(file)
    path.write_text(header + "\n\n" + body + ("\n" if body else ""), encoding="utf-8")
    return path.resolve()


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
