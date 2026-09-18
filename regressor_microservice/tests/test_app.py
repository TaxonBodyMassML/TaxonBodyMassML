"""
Tests for the Flask microservice, run against the package's cached artifacts.

Run from regressor_microservice/:
    .venv/bin/pytest -q

The tests skip unless the taxonbodymassml package cache already holds the
artifacts (set TBM_ALLOW_DOWNLOAD=1 to let the package download ~0.4 GB).
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
FUNGUS = {
    "kingdom": "Fungi",
    "phylum": "Basidiomycota",
    "class": "Agaricomycetes",
    "order": "Agaricales",
    "family": "Agaricaceae",
    "genus": "Agaricus",
    "species": "Agaricus bisporus",
}


@pytest.fixture(scope="session")
def client():
    from taxonbodymassml._model import _CACHE_DIR

    needed = ["model_ee.ubj", "embeddings.json", "categories.json", "lookup.json"]
    if os.environ.get("TBM_ALLOW_DOWNLOAD") != "1" and not all(
        (_CACHE_DIR / f).exists() for f in needed
    ):
        pytest.skip("model artifacts not in the package cache (set TBM_ALLOW_DOWNLOAD=1)")
    import regressor

    return regressor.create_wsgi_app().test_client()


def _state(client):
    return client.application.config["state"]


def test_health_reports_method_and_versions(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["status"] == "ok"
    assert body["method"] == _state(client).method
    assert body["package_version"] and body["model_artifact_version"]


def test_known_species_returns_recorded_mass(client):
    lookup = _state(client).lookup
    species = "Nucella ostrina"  # in the training data (see R test suite)
    assert species in lookup
    resp = client.post("/xgb_pred_single", json={"genus": "Nucella", "species": species})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert body["prediction"] == lookup[species]["mass_g"]
    assert body["lower_bound"] == body["upper_bound"] == body["prediction"]
    assert body["confidence"] is None
    assert body["source"] == lookup[species]["source"]
    assert body["model"] is None
    assert body["taxonomy"]["species"] == species


def test_unknown_species_is_model_inferred(client):
    resp = client.post("/xgb_pred_single", json={**CANIS, "species": "Canis notarealwolf"})
    assert resp.status_code == 200, resp.get_json()
    body = resp.get_json()
    assert all(isinstance(body[k], float) for k in ("prediction", "lower_bound", "upper_bound"))
    assert body["lower_bound"] < body["prediction"] < body["upper_bound"]
    assert body["confidence"] == 0.90
    assert body["source"] == "tbmML_genus"
    assert body["model"] == _state(client).method
    # Species is not a model feature: the genus-level query gives the same answer.
    genus_only = client.post("/xgb_pred_single", json=CANIS).get_json()
    assert genus_only["taxonomy"]["species"] == "UNK"
    assert np.isclose(body["prediction"], genus_only["prediction"])


def test_family_level_query_has_wider_interval_than_genus_level(client):
    genus = client.post("/xgb_pred_single", json=CANIS).get_json()
    family = client.post("/xgb_pred_single", json={**CANIS, "genus": "UNK"}).get_json()
    assert family["source"] == "tbmML_family"
    ratio = lambda b: b["upper_bound"] / b["lower_bound"]  # noqa: E731
    assert ratio(family) > ratio(genus)


def test_unrepresented_taxonomy_returns_null_with_warning(client):
    for payload in ({c: "UNK" for c in TAXONOMY_COLS}, FUNGUS):
        resp = client.post("/xgb_pred_single", json=payload)
        assert resp.status_code == 200, resp.get_json()
        body = resp.get_json()
        assert body["prediction"] is None
        assert body["lower_bound"] is None and body["upper_bound"] is None
        assert body["confidence"] is None
        assert body["source"] == "tbmML_UNK"
        assert body["model"] is None
        assert "represented in the training data" in body["warning"]


def test_unseen_values_map_to_unk(client):
    resp = client.post("/xgb_pred_single", json={"genus": "Notagenus", "species": "Not a species"})
    assert resp.status_code == 200
    assert resp.get_json()["taxonomy"]["genus"] == "UNK"


def test_multi_prediction_preserves_order_and_mixes_outcomes(client):
    payload = [
        {**CANIS, "species": "Canis notarealwolf"},  # model
        FUNGUS,  # unrepresented -> null
        {"genus": "Nucella", "species": "Nucella ostrina"},  # dictionary
        {"genus": "Mus", "species": "Mus notarealmouse"},  # model
    ]
    resp = client.post("/xgb_pred_multi", json=payload)
    assert resp.status_code == 200
    items = resp.get_json()["items"]
    assert len(items) == 4
    assert items[0]["model"] is not None and items[0]["prediction"] > items[3]["prediction"]
    assert items[1]["prediction"] is None and "warning" in items[1]
    assert items[2]["source"] == _state(client).lookup["Nucella ostrina"]["source"]
    assert items[3]["source"] == "tbmML_genus"


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
    key = {"EntityEmbeddings": "log10_mass_g_ee", "XGBoost": "log10_mass_g"}[_state(client).method]
    if not all(key in c for c in cases):
        pytest.skip(f"golden file has no {key}")
    resp = client.post("/xgb_pred_multi", json=[{c: k[c] for c in TAXONOMY_COLS} for k in cases])
    lookup = _state(client).lookup
    items = resp.get_json()["items"]
    dict_rows = [(c, it) for c, it in zip(cases, items) if c["species"] in lookup]
    na_rows = [
        (c, it) for c, it in zip(cases, items) if c.get("expect_na") and c["species"] not in lookup
    ]
    model_rows = [
        (c, it)
        for c, it in zip(cases, items)
        if c["species"] not in lookup and not c.get("expect_na")
    ]
    assert model_rows and dict_rows and na_rows  # golden set exercises all three paths
    got = np.log10([it["prediction"] for _, it in model_rows])
    expected = np.array([c[key] for c, _ in model_rows])
    assert np.max(np.abs(got - expected)) < 1e-5
    for c, it in dict_rows:
        assert it["prediction"] == lookup[c["species"]]["mass_g"]
        assert it["confidence"] is None
    for _, it in na_rows:
        assert it["prediction"] is None and it["source"] == "tbmML_UNK"
