"""
pasquang
pasquang@oregonstate.edu
4/10/2026
"""

# run using: gunicorn -w 1 -b 127.0.0.1:8000 'regressor:create_wsgi_app()'

import os
import traceback
import unicodedata

import pandas as pd
import pickleslicer
from flask import Flask, jsonify, request
from flask_cors import CORS

MODEL_READ_FILE = "./sliced_model/xgboost_model.pkl"
TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
# Model features: kingdom .. genus.  Species is not a feature; it is used for the
# training-data dictionary lookup and for genus promotion only.
MODEL_FEATURES = ["kingdom", "phylum", "class", "order", "family", "genus"]
RANK_ORDER = ["genus", "family", "order", "class", "phylum", "kingdom"]
UNK = "UNK"
_GBIF_KINGDOM_NORM: dict[str, str] = {
    "Metazoa": "Animalia",
    "Plantae": "Viridiplantae",
}


class ModelState:
    """Everything derived from the pickle bundle, computed once at startup."""

    def __init__(self, bundle):
        self.model = bundle["model"]
        self.q = float(bundle["q"])
        vocab = bundle["vocab"]  # {feature: [UNK, sorted training values...]}
        self.vocab = vocab
        self.valid = {col: set(vocab[col]) for col in MODEL_FEATURES}
        self.genus_vocab = self.valid["genus"] - {UNK}
        self.dtypes = {col: pd.CategoricalDtype(categories=vocab[col]) for col in MODEL_FEATURES}
        # species -> {mass_g, source} from the training data (same as lookup.json)
        self.lookup = bundle["lookup"]
        # Column order is dictated by the model; never assume MODEL_FEATURES.
        self.feature_names = list(self.model.get_booster().feature_names or [])
        if set(self.feature_names) != set(MODEL_FEATURES):
            raise RuntimeError(
                f"Model feature_names {self.feature_names} do not match {MODEL_FEATURES}; "
                "retrain with predictive_models/decision_tree.py"
            )


def _ascii_normalize(x):
    if pd.isna(x):
        return None
    normalized = unicodedata.normalize("NFKD", str(x))
    return normalized.encode("ascii", "ignore").decode("ascii")


def _normalize_taxonomy(df, state):
    """Return df[TAXONOMY_COLS] as strings after ASCII normalization, UNK mapping, genus promotion.

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


def _encode_taxonomy(df_str, state):
    """Categorical frame (categories == training vocab) in the model's feature order."""
    encoded = pd.DataFrame({col: df_str[col].astype(state.dtypes[col]) for col in MODEL_FEATURES})
    return encoded[state.feature_names]


def _source_rank(row, state):
    """'tbmML_<finest rank present in training>' for a model-inferred row."""
    for rank in RANK_ORDER:
        if row[rank] != UNK:
            return f"tbmML_{rank}"
    return "tbmML_UNK"


def _validate_records(data):
    """Return a list of taxonomy dicts or raise ValueError for a malformed payload."""
    records = data if isinstance(data, list) else [data]
    if not records or not all(isinstance(r, dict) for r in records):
        raise ValueError("Payload must be a JSON object or a non-empty list of JSON objects")
    if not any(any(col in r for col in TAXONOMY_COLS) for r in records):
        raise ValueError(f"No taxonomy fields provided; expected any of {TAXONOMY_COLS}")
    return records


def _predict_rows(records, state):
    """One result per record.

    Species with a recorded mass in the training data return that value with a
    degenerate interval and their data source (mirrors the packages' dictionary
    lookup).  Everything else is model-inferred from kingdom..genus with a 90%
    conformal interval.
    """
    df_str = _normalize_taxonomy(pd.DataFrame(records), state)
    preds = state.model.predict(_encode_taxonomy(df_str, state))
    results = []
    for row_dict, pred in zip(df_str.to_dict(orient="records"), preds):
        taxonomy = {col: str(row_dict[col]) for col in TAXONOMY_COLS}
        hit = state.lookup.get(row_dict["species"])
        if hit is not None:
            mass = float(hit["mass_g"])
            results.append(
                {
                    "taxonomy": taxonomy,
                    "prediction": mass,
                    "lower_bound": mass,
                    "upper_bound": mass,
                    "confidence": None,
                    "source": str(hit["source"]),
                }
            )
            continue
        pred = float(pred)
        results.append(
            {
                "taxonomy": taxonomy,
                "prediction": float(10**pred),
                "lower_bound": float(10 ** (pred - state.q)),
                "upper_bound": float(10 ** (pred + state.q)),
                "confidence": 0.90,
                "source": _source_rank(row_dict, state),
            }
        )
    return results


def _load_state():
    bundle = pickleslicer.load(MODEL_READ_FILE)
    if not bundle.get("model"):
        print("Model not loaded successfully.")
        raise RuntimeError("Model not loaded successfully.")
    state = ModelState(bundle)
    print("Model loaded successfully.")

    # Warm up XGBoost's OpenMP thread pool so the first real request isn't penalized.
    _predict_rows([{col: UNK for col in TAXONOMY_COLS}], state)
    return state


def create_app(state):
    app = Flask(__name__)
    CORS(app)
    app.config["state"] = state

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

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
            <title>Model API</title>
        </head>
        <body>
            <h1>Model server is running!</h1>
            <p>The very first prediction request may take a little while to complete.
               Subsequent requests will be significantly faster.</p>
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
