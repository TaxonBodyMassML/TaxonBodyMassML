"""
TaxonBodyMassML prediction microservice (backend of https://taxonbodymassml.github.io).

The service answers every request with ``taxonbodymassml.predict_mass`` from
the released Python package, so the web interface, the R package and the
Python package share one inference implementation.  The package is installed
from its release wheel (see the dockerfile) and the model artifacts are
downloaded from Hugging Face at image build time, so the container starts
offline.  Endpoint paths and the response schema are unchanged from the
original XGBoost-only service so the front end keeps working.

Run locally (after ``pip install -r requirements.txt`` and the package):
    gunicorn -w 1 -b 127.0.0.1:8000 'regressor:create_wsgi_app()'

Environment:
    TBM_METHOD   prediction method served: "EntityEmbeddings" (default) or "XGBoost"

Response schema (one object per taxonomy):
    taxonomy      the seven ranks after normalisation (unseen values -> "UNK")
    prediction    grams; null when no rank of the taxonomy is in the training data
    lower_bound,  90% rank-stratified conformal interval in grams (equal to the
    upper_bound   prediction for species taken from the training-data dictionary;
                  null when prediction is null)
    confidence    0.90 for model predictions, null otherwise
    source        data-source label for dictionary species, "tbmML_<rank>" for
                  model predictions, "tbmML_UNK" when nothing is represented
    model         "EntityEmbeddings" / "XGBoost" for model predictions, else null
    warning       present only when prediction is null
"""

import math
import os
import traceback
import unicodedata
import warnings
from importlib import metadata

import pandas as pd
import taxonbodymassml
from flask import Flask, jsonify, request
from flask_cors import CORS

# These helpers are private to the package.  The service pins the package
# version (dockerfile ARG TBM_WHEEL), so relying on them is safe; they provide
# the UNK-mapped taxonomy echo and the dictionary that the response schema needs.
from taxonbodymassml._checksums import MODEL_ARTIFACT_VERSION
from taxonbodymassml._model import _ensure_artifacts, load_categories, load_lookup

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
# Model features: kingdom .. genus.  Species is not a feature; it is used for the
# training-data dictionary lookup and for genus promotion only.
MODEL_FEATURES = ["kingdom", "phylum", "class", "order", "family", "genus"]
UNK = "UNK"
METHODS = ("EntityEmbeddings", "XGBoost")
METHOD = os.environ.get("TBM_METHOD", "EntityEmbeddings")
INTERVAL_METHOD = "stratified"
CONFIDENCE = 0.90
UNREPRESENTED_WARNING = (
    "No rank of the supplied taxonomy is represented in the training data; "
    "no prediction is possible"
)
_GBIF_KINGDOM_NORM: dict[str, str] = {
    "Metazoa": "Animalia",
    "Plantae": "Viridiplantae",
}


def _package_version() -> str:
    try:
        return metadata.version("taxonbodymassml")
    except metadata.PackageNotFoundError:  # editable/source checkouts
        return getattr(taxonbodymassml, "__version__", "unknown")


class ModelState:
    """Everything the request handlers need, prepared once at startup."""

    def __init__(self, method: str = METHOD):
        if method not in METHODS:
            raise ValueError(f"TBM_METHOD must be one of {METHODS}; got {method!r}")
        self.method = method
        _ensure_artifacts()  # verifies the cached artifacts against the package checksums
        self.categories = load_categories()  # {feature: [UNK, sorted training values...]}
        self.valid = {col: set(self.categories[col]) for col in MODEL_FEATURES}
        self.genus_vocab = self.valid["genus"] - {UNK}
        self.lookup = load_lookup()  # species -> {mass_g, source}
        self.package_version = _package_version()
        self.artifact_version = MODEL_ARTIFACT_VERSION


def _ascii_normalize(x):
    if pd.isna(x):
        return None
    normalized = unicodedata.normalize("NFKD", str(x))
    return normalized.encode("ascii", "ignore").decode("ascii")


def _normalize_taxonomy(df, state):
    """Return df[TAXONOMY_COLS] as strings after ASCII normalisation, UNK mapping, genus promotion.

    Model features are mapped to the training vocabulary (unseen -> UNK); the
    species column is kept as the normalised input (or UNK) for the dictionary
    lookup and the response.
    """
    df = df.copy()
    for col in TAXONOMY_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_ascii_normalize)
        else:
            df[col] = UNK
    df["species"] = df["species"].fillna(UNK)
    df["kingdom"] = df["kingdom"].map(lambda x: _GBIF_KINGDOM_NORM.get(x, x))
    # Genus names queried via NCBI land in the species slot with genus left as
    # "UNK". Promote them to the correct slot so the model uses the genus.
    genus_unk = df["genus"].isin([UNK]) | df["genus"].isna()
    sp_is_genus = df["species"].isin(state.genus_vocab)
    promote = genus_unk & sp_is_genus
    df.loc[promote, "genus"] = df.loc[promote, "species"]
    df.loc[promote, "species"] = UNK
    for col in MODEL_FEATURES:
        df[col] = df[col].where(df[col].isin(state.valid[col]), other=UNK)
    return df[TAXONOMY_COLS]


def _is_missing(value) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _validate_records(data):
    """Return a list of taxonomy dicts or raise ValueError for a malformed payload."""
    records = data if isinstance(data, list) else [data]
    if not records or not all(isinstance(r, dict) for r in records):
        raise ValueError("Payload must be a JSON object or a non-empty list of JSON objects")
    if not any(any(col in r for col in TAXONOMY_COLS) for r in records):
        raise ValueError(f"No taxonomy fields provided; expected any of {TAXONOMY_COLS}")
    return records


def _predict_rows(records, state):
    """One result per record, in input order.

    Species with a recorded mass in the training data return that value with a
    degenerate interval and their data source.  Everything else is predicted by
    the package from kingdom..genus with a 90% rank-stratified conformal
    interval.  Taxa with no rank in the training data get a null prediction and
    a warning instead of an extrapolation from all-unknown features.
    """
    df_str = _normalize_taxonomy(pd.DataFrame(records), state)
    df_in = df_str.rename(columns={"species": "species_resolved"})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # unrepresented rows are reported per item below
        out = taxonbodymassml.predict_mass(
            df_in,
            confidence_interval=CONFIDENCE,
            method=state.method,
            interval_method=INTERVAL_METHOD,
            include_source=True,
            lookup=True,
        )

    results = []
    for row_dict, res in zip(df_str.to_dict(orient="records"), out.to_dict(orient="records")):
        taxonomy = {col: str(row_dict[col]) for col in TAXONOMY_COLS}
        source = res.get("source")
        mass = res.get("mass_g")

        if _is_missing(mass) or source == "tbmML_UNK" or source is None:
            results.append(
                {
                    "taxonomy": taxonomy,
                    "prediction": None,
                    "lower_bound": None,
                    "upper_bound": None,
                    "confidence": None,
                    "source": "tbmML_UNK",
                    "model": None,
                    "warning": UNREPRESENTED_WARNING,
                }
            )
            continue

        mass = float(mass)
        if not str(source).startswith("tbmML_"):  # training-data dictionary hit
            results.append(
                {
                    "taxonomy": taxonomy,
                    "prediction": mass,
                    "lower_bound": mass,
                    "upper_bound": mass,
                    "confidence": None,
                    "source": str(source),
                    "model": None,
                }
            )
            continue

        lower, upper = res.get("lower_bound"), res.get("upper_bound")
        results.append(
            {
                "taxonomy": taxonomy,
                "prediction": mass,
                "lower_bound": mass if _is_missing(lower) else float(lower),
                "upper_bound": mass if _is_missing(upper) else float(upper),
                "confidence": CONFIDENCE,
                "source": str(source),
                "model": state.method,
            }
        )
    return results


def _load_state():
    state = ModelState()
    print(
        f"Model loaded successfully: method={state.method}, "
        f"taxonbodymassml {state.package_version}, artifacts {state.artifact_version}."
    )
    # Warm up the model and XGBoost's thread pool so the first request isn't penalized.
    _predict_rows([{"kingdom": "Animalia"}], state)
    return state


def create_app(state):
    app = Flask(__name__)
    CORS(app)
    app.config["state"] = state

    @app.route("/health", methods=["GET"])
    def health():
        return (
            jsonify(
                {
                    "status": "ok",
                    "method": state.method,
                    "package_version": state.package_version,
                    "model_artifact_version": state.artifact_version,
                }
            ),
            200,
        )

    @app.route("/xgb_pred_single", methods=["POST"])
    def xgb_pred_single():
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, dict):
                return jsonify({"error": "Payload must be a single JSON object"}), 400
            records = _validate_records(data)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        try:
            return jsonify(_predict_rows(records, app.config["state"])[0])
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route("/xgb_pred_multi", methods=["POST"])
    def xgb_pred_multi():
        try:
            data = request.get_json(silent=True)
            if not isinstance(data, list):
                return jsonify({"error": "Payload must be a JSON list of objects"}), 400
            records = _validate_records(data)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        try:
            return jsonify({"items": _predict_rows(records, app.config["state"])})
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route("/", methods=["GET"])
    def home():
        return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>TaxonBodyMassML API</title>
        </head>
        <body>
            <h1>Model server is running!</h1>
            <p>POST a taxonomy to /xgb_pred_single or a list to /xgb_pred_multi;
               GET /health for the served method and versions.</p>
        </body>
    </html>
    """

    return app


def create_wsgi_app():
    return create_app(_load_state())


def main():
    app = create_app(_load_state())
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
