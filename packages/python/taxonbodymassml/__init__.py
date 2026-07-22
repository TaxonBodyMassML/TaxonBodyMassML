"""
taxonbodymassml — Predict species body mass using the TaxonBodyMassML XGBoost model.

Quick start::

    import taxonbodymassml as tbm
    tbm.predict_mass("Haustrum scobina")
    tbm.predict_mass(["Haustrum scobina", "Mus musculus"], confidence_interval=True)
"""

__version__ = "0.1.0"

from ._lookup import tbm_clear_cache, lookup_taxonomy, tbm_options
from ._model import download_model
from ._predict import predict_mass

__all__ = [
    "predict_mass",
    "lookup_taxonomy",
    "download_model",
    "get_citations",
    "tbm_options",
    "tbm_clear_cache",
]


def get_citations():
    """Return the path to the bundled Citations_BodyMass.bib file.

    The BibTeX file lists all data sources used to train the TaxonBodyMassML
    model.  Pass the path to ``bibtexparser.load()`` or open it in any
    reference manager (Zotero, BibDesk, JabRef, etc.).

    Returns
    -------
    pathlib.Path
        Absolute path to ``taxonbodymassml/data/Citations_BodyMass.bib``.
    """
    from pathlib import Path
    return Path(__file__).parent / "data" / "Citations_BodyMass.bib"
