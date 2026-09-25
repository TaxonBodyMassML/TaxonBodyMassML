"""
taxonbodymassml — Predict species body mass using the TaxonBodyMassML XGBoost model.

Quick start::

    import taxonbodymassml as tbm
    tbm.predict_mass("Haustrum scobina")
    tbm.predict_mass(["Haustrum scobina", "Mus musculus"], confidence_interval=True)
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("taxonbodymassml")
except PackageNotFoundError:
    __version__ = "unknown"

from ._citations import create_bib, get_citations
from ._fuzzy import correct_species_names, fuzzy_lookup_taxonomy, fuzzy_predict_mass
from ._lookup import lookup_taxonomy, tbm_clear_cache, tbm_options
from ._model import download_model
from ._predict import predict_mass

__all__ = [
    "predict_mass",
    "lookup_taxonomy",
    "correct_species_names",
    "fuzzy_lookup_taxonomy",
    "fuzzy_predict_mass",
    "download_model",
    "get_citations",
    "create_bib",
    "tbm_options",
    "tbm_clear_cache",
]
