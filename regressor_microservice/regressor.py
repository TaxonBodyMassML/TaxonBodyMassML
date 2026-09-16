"""
pasquang
pasquang@oregonstate.edu
4/10/2026
"""

# run using: gunicorn -w 1 -b 127.0.0.1:8000 'regressor:create_wsgi_app()'

import json
import os
import traceback
import unicodedata

import pandas as pd
import pickleslicer
from flask import Flask, jsonify, request
from flask_cors import CORS

MODEL_READ_FILE = "./sliced_model/xgboost_model.pkl"
TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
_GBIF_KINGDOM_NORM: dict[str, str] = {
    "Metazoa": "Animalia",
    "Plantae": "Viridiplantae",
}


def _extract_categories(model):
    """Extract per-column category lists in training-time integer-code order."""
    booster = model.get_booster() if hasattr(model, "get_booster") else model
    model_raw = json.loads(booster.save_raw(raw_format="json"))
    cats_data = model_raw["learner"]["gradient_booster"]["model"]["cats"]
    enc = cats_data["enc"]
    feature_names = model_raw["learner"]["feature_names"]

    categories = {}
    for feat_idx, fname in enumerate(feature_names):
        e = enc[feat_idx]
        offsets = e["offsets"]
        values = e["values"]
        categories[fname] = [
            bytes(v & 0xFF for v in values[offsets[i] : offsets[i + 1]]).decode("utf-8")
            for i in range(len(offsets) - 1)
        ]
    return categories


def _ascii_normalize(x):
    if pd.isna(x):
        return None
    normalized = unicodedata.normalize("NFKD", str(x))
    return normalized.encode("ascii", "ignore").decode("ascii")


def _apply_categories(df, categories):
    """Replace unknown taxonomy values with 'UNK' and encode as Categorical."""
    df = df.copy()
    for col in TAXONOMY_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_ascii_normalize)
    if "kingdom" in df.columns:
        df["kingdom"] = df["kingdom"].map(lambda x: _GBIF_KINGDOM_NORM.get(x, x))
    # Genus names queried via NCBI land in the species slot with genus left as
    # "UNK". Promote them to the correct slot so the model uses genus embeddings.
    if "genus" in df.columns and "species" in df.columns:
        genus_vocab = set(categories.get("genus", [])) - {"UNK"}
        genus_unk = df["genus"].isin(["UNK"]) | df["genus"].isna()
        sp_is_genus = df["species"].isin(genus_vocab)
        promote = genus_unk & sp_is_genus
        df.loc[promote, "genus"] = df.loc[promote, "species"]
        df.loc[promote, "species"] = "UNK"
    for col in TAXONOMY_COLS:
        if col not in df.columns:
            continue
        valid = set(categories[col])
        df[col] = df[col].where(df[col].isin(valid), other="UNK")
        df[col] = pd.Categorical(df[col], categories=categories[col])
    return df[TAXONOMY_COLS]


def _load_state():
    loaded_bundle = pickleslicer.load(MODEL_READ_FILE)
    model = loaded_bundle["model"]
    q = float(loaded_bundle["q"])

    if not model:
        print("Model not loaded successfully.")
        raise RuntimeError("Model not loaded successfully.")

    print("Model loaded successfully.")
    categories = _extract_categories(model)

    # Warm up XGBoost's OpenMP thread pool so the first real request isn't penalized.
    warmup = _apply_categories(
        pd.DataFrame([{col: "UNK" for col in TAXONOMY_COLS}]), categories
    )  # noqa: E501
    model.predict(warmup)

    return model, q, categories


def create_app(model, q, categories):
    app = Flask(__name__)
    CORS(app)

    app.config["model"] = model
    app.config["q"] = q
    app.config["categories"] = categories

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok"}), 200

    @app.route("/xgb_pred_single", methods=["POST"])
    def xgb_pred_single():
        try:
            model = app.config["model"]
            q = app.config["q"]
            categories = app.config["categories"]

            data = request.json
            df = _apply_categories(pd.DataFrame([data]), categories)

            if df.empty:
                return jsonify({"error": "No valid taxonomy data provided"}), 400

            prediction_log = float(model.predict(df)[0])

            return jsonify(
                {
                    "taxonomy": {col: df[col].iloc[0] for col in TAXONOMY_COLS},
                    "prediction": float(10**prediction_log),
                    "lower_bound": float(10 ** (prediction_log - q)),
                    "upper_bound": float(10 ** (prediction_log + q)),
                    "confidence": 0.90,
                }
            )
        except Exception as e:
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route("/xgb_pred_multi", methods=["POST"])
    def xgb_pred_multi():
        try:
            model = app.config["model"]
            q = app.config["q"]
            categories = app.config["categories"]

            data = request.json
            df = _apply_categories(pd.DataFrame(data), categories)

            if df.empty:
                return jsonify({"error": "No valid taxonomy data provided"}), 400

            predictions = model.predict(df)
            results = []
            for row_dict, pred in zip(df.to_dict(orient="records"), predictions):
                pred = float(pred)
                results.append(
                    {
                        "taxonomy": {col: row_dict[col] for col in TAXONOMY_COLS},
                        "prediction": float(10**pred),
                        "lower_bound": float(10 ** (pred - q)),
                        "upper_bound": float(10 ** (pred + q)),
                        "confidence": 0.90,
                    }
                )
            return jsonify({"items": results})
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
    model, q, categories = _load_state()
    return create_app(model, q, categories)


def main():
    model, q, categories = _load_state()
    app = create_app(model, q, categories)
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
