"""
Smoke tests for the Flask microservice against the real pickle bundle.

Run from regressor_microservice/:
    .venv/bin/pytest -q
"""

import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

TAXONOMY_COLS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
CANIS = {
    "kingdom": "Animalia",
    "phylum": "Chordata",
    "class": "Mammalia",
    "order": "Carnivora",
    "family": "Canidae",
    "genus": "Canis",
}


@pytest.fixture(scope="session")
def client():
    if not (HERE / "sliced_model" / "xgboost_model.pkl.1").exists():
        pytest.skip("pickle bundle not present")
    cwd = os.getcwd()
    os.chdir(HERE)
    try:
        import regressor

        app = regressor.create_wsgi_app()
    finally:
        os.chdir(cwd)
    return app.test_client()


def test_health(client):
    assert client.get("/health").status_code == 200


def test_known_species_returns_recorded_mass(client):
    lookup = client.application.config["state"].lookup
    species = "Nucella ostrina"  # in the training data (see R test suite)
    assert species in lookup
    resp = client.post("/xgb_pred_single", json={"genus": "Nucella", "species": species})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["prediction"] == lookup[species]["mass_g"]
    assert body["lower_bound"] == body["upper_bound"] == body["prediction"]
    assert body["confidence"] is None
    assert body["source"] == lookup[species]["source"]
    assert body["taxonomy"]["species"] == species


def test_unknown_species_is_model_inferred(client):
    resp = client.post("/xgb_pred_single", json={**CANIS, "species": "Canis notarealwolf"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["lower_bound"] < body["prediction"] < body["upper_bound"]
    assert body["confidence"] == 0.90
    assert body["source"] == "tbmML_genus"
    # Species is not a model feature: the genus-level query gives the same answer.
    genus_only = client.post("/xgb_pred_single", json=CANIS).get_json()
    assert np.isclose(body["prediction"], genus_only["prediction"])


def test_genus_level_query_differs_from_all_unk(client):
    all_unk = client.post("/xgb_pred_single", json={c: "UNK" for c in TAXONOMY_COLS}).get_json()
    canis = client.post("/xgb_pred_single", json=CANIS).get_json()
    assert canis["taxonomy"]["species"] == "UNK"
    assert not np.isclose(canis["prediction"], all_unk["prediction"])


def test_unseen_values_map_to_unk(client):
    resp = client.post("/xgb_pred_single", json={"genus": "Notagenus", "species": "Not a species"})
    assert resp.status_code == 200
    assert resp.get_json()["taxonomy"]["genus"] == "UNK"


def test_multi_prediction(client):
    payload = [
        {**CANIS, "species": "Canis notarealwolf"},
        {"genus": "Mus", "species": "Mus notarealmouse"},
    ]
    resp = client.post("/xgb_pred_multi", json=payload)
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 2
    assert items[0]["prediction"] > items[1]["prediction"]


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("/xgb_pred_single", {"colour": "red"}),
        ("/xgb_pred_single", [{"genus": "Canis"}]),
        ("/xgb_pred_single", "not json"),
        ("/xgb_pred_multi", []),
        ("/xgb_pred_multi", {"genus": "Canis"}),
        ("/xgb_pred_multi", [1, 2]),
    ],
)
def test_malformed_payloads_return_400(client, endpoint, payload):
    resp = client.post(endpoint, json=payload)
    assert resp.status_code == 400, resp.get_json()


def test_golden_predictions(client):
    golden = HERE.parent / "predictive_models" / "results" / "golden_predictions.json"
    if not golden.exists():
        pytest.skip("golden_predictions.json not present; run scripts/export_artifacts.py")
    cases = json.loads(golden.read_text())["cases"]
    resp = client.post("/xgb_pred_multi", json=[{c: k[c] for c in TAXONOMY_COLS} for k in cases])
    lookup = client.application.config["state"].lookup
    items = resp.get_json()["items"]
    model_rows = [(c, it) for c, it in zip(cases, items) if c["species"] not in lookup]
    dict_rows = [(c, it) for c, it in zip(cases, items) if c["species"] in lookup]
    assert model_rows and dict_rows  # golden set exercises both paths
    got = np.log10([it["prediction"] for _, it in model_rows])
    expected = np.array([c["log10_mass_g"] for c, _ in model_rows])
    assert np.max(np.abs(got - expected)) < 1e-5
    for c, it in dict_rows:
        assert it["prediction"] == lookup[c["species"]]["mass_g"]
        assert it["confidence"] is None
