"""
Tests for taxonbodymassml.predict_mass().

Tests that require model artifacts (the ~0.6 GB download) are skipped
unless TAXONBODYMASSML_RUN_INTEGRATION=1 is set in the environment.
"""

import os
import warnings

import pandas as pd
import pytest

INTEGRATION = os.environ.get("TAXONBODYMASSML_RUN_INTEGRATION", "0") == "1"
skip_without_artifacts = pytest.mark.skipif(
    not INTEGRATION,
    reason="Requires model artifacts; set TAXONBODYMASSML_RUN_INTEGRATION=1",
)


# ---------------------------------------------------------------------------
# Unit tests (no artifacts required)
# ---------------------------------------------------------------------------
def test_resolve_ci_level_false():
    from taxonbodymassml._predict import _resolve_ci_level

    assert _resolve_ci_level(False) is None


def test_resolve_ci_level_true():
    from taxonbodymassml._predict import _resolve_ci_level

    assert _resolve_ci_level(True) == 0.90


def test_resolve_ci_level_float():
    from taxonbodymassml._predict import _resolve_ci_level

    assert _resolve_ci_level(0.80) == pytest.approx(0.80)


def test_resolve_ci_level_invalid():
    from taxonbodymassml._predict import _resolve_ci_level

    with pytest.raises(ValueError):
        _resolve_ci_level(1.5)
    with pytest.raises(ValueError):
        _resolve_ci_level(0.0)


def test_predict_unknown_method():
    import taxonbodymassml as tbm

    with pytest.raises(ValueError, match="Unknown method"):
        tbm.predict_mass("Mus musculus", method="RandomForest")


def test_predict_dataframe_missing_columns():
    import taxonbodymassml as tbm

    with pytest.raises(ValueError, match="missing taxonomy columns"):
        tbm.predict_mass(pd.DataFrame({"kingdom": ["Animalia"]}))


# ---------------------------------------------------------------------------
# Integration tests (require artifacts + network)
# ---------------------------------------------------------------------------
@skip_without_artifacts
def test_predict_single_species():
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Mus musculus")
    assert isinstance(result, pd.DataFrame)
    assert "mass_g" in result.columns
    assert result["mass_g"].iloc[0] > 0


@skip_without_artifacts
def test_predict_confidence_interval_true():
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Mus musculus", confidence_interval=True, lookup=False)
    assert "lower_bound" in result.columns
    assert "upper_bound" in result.columns
    assert result["confidence"].iloc[0] == pytest.approx(0.90)
    assert result["lower_bound"].iloc[0] < result["mass_g"].iloc[0]
    assert result["upper_bound"].iloc[0] > result["mass_g"].iloc[0]


@skip_without_artifacts
def test_predict_confidence_interval_custom():
    import taxonbodymassml as tbm

    r90 = tbm.predict_mass("Mus musculus", confidence_interval=0.90, lookup=False)
    r80 = tbm.predict_mass("Mus musculus", confidence_interval=0.80, lookup=False)
    width90 = r90["upper_bound"].iloc[0] - r90["lower_bound"].iloc[0]
    width80 = r80["upper_bound"].iloc[0] - r80["lower_bound"].iloc[0]
    assert width90 > width80  # wider interval at higher coverage


@skip_without_artifacts
def test_predict_include_taxonomy():
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Mus musculus", include_taxonomy=True)
    assert "kingdom" in result.columns
    assert "species_resolved" in result.columns


@skip_without_artifacts
def test_predict_unresolvable_species():
    import taxonbodymassml as tbm

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = tbm.predict_mass("xxxxnotaspeciesxxxx")
    assert any("No species could be resolved" in str(warning.message) for warning in w)
    import math

    assert math.isnan(result["mass_g"].iloc[0])


@skip_without_artifacts
def test_predict_list():
    import taxonbodymassml as tbm

    result = tbm.predict_mass(["Mus musculus", "Panthera leo"])
    assert len(result) == 2
    assert all(result["mass_g"] > 0)


@skip_without_artifacts
def test_predict_taxonomy_dataframe_input():
    import taxonbodymassml as tbm

    tax = tbm.lookup_taxonomy("Mus musculus")
    result = tbm.predict_mass(tax)
    assert result["mass_g"].iloc[0] > 0


# ---------------------------------------------------------------------------
# fuzzy_match_name column semantics
# ---------------------------------------------------------------------------


@skip_without_artifacts
def test_fuzzy_match_corrected_name_in_species_original_in_matched_name():
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Ballanus glandula", fuzzy_match_name=True)
    assert result["taxon"].iloc[0] == "Balanus glandula"
    assert result["matched_name"].iloc[0] == "Ballanus glandula"
    assert "matched_name" in result.columns


@skip_without_artifacts
def test_fuzzy_match_matched_name_none_when_no_correction_needed():
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Balanus glandula", fuzzy_match_name=True)
    assert result["taxon"].iloc[0] == "Balanus glandula"
    assert result["matched_name"].iloc[0] is None
    assert "matched_name" in result.columns


@skip_without_artifacts
def test_fuzzy_match_species_none_and_matched_name_set_when_gbif_finds_no_match():
    import math

    import taxonbodymassml as tbm

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = tbm.predict_mass(
            "Xyzzy_definitely_not_a_species_12345", fuzzy_match_name=True
        )  # noqa: E501
    assert result["taxon"].iloc[0] is None
    assert result["matched_name"].iloc[0] == "Xyzzy_definitely_not_a_species_12345"
    assert math.isnan(result["mass_g"].iloc[0])


# ---------------------------------------------------------------------------
# Dictionary lookup and include_source
# ---------------------------------------------------------------------------


@skip_without_artifacts
def test_dict_hit_returns_empirical_mass():
    """Nucella ostrina is in training data with mass_g=0.7."""
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Nucella ostrina")
    assert result["mass_g"].iloc[0] == pytest.approx(0.7)


@skip_without_artifacts
def test_include_source_dict_hit_returns_source_string():
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Nucella ostrina", include_source=True)
    assert "source" in result.columns
    assert result["source"].iloc[0] == "Novak_unpubl"


@skip_without_artifacts
def test_dict_hit_ci_columns_are_nan():
    import math

    import taxonbodymassml as tbm

    result = tbm.predict_mass("Nucella ostrina", confidence_interval=True)
    assert "lower_bound" in result.columns
    assert math.isnan(result["lower_bound"].iloc[0])
    assert math.isnan(result["upper_bound"].iloc[0])
    assert math.isnan(result["confidence"].iloc[0])


@skip_without_artifacts
def test_include_source_model_inferred_genus_known():
    """Nucella lima is not in training data but the genus Nucella is known."""
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Nucella lima", include_source=True)
    assert "source" in result.columns
    assert result["source"].iloc[0] == "tbmML_genus"


@skip_without_artifacts
def test_include_source_unresolvable_returns_none():
    import taxonbodymassml as tbm

    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = tbm.predict_mass(
            "Xyzzy_definitely_not_a_species_12345", include_source=True
        )  # noqa: E501
    assert "source" in result.columns
    assert result["source"].iloc[0] is None


@skip_without_artifacts
def test_mixed_dict_model_unresolved_order_preserved():
    """Output order is preserved across dict hits, model rows, and unresolved."""
    import math

    import taxonbodymassml as tbm

    sp = [
        "Nucella ostrina",  # dict hit
        "Canis lupus",  # model-inferred
        "Xyzzy_definitely_not_a_species_12345",  # unresolvable
    ]
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        result = tbm.predict_mass(sp, include_source=True)

    assert len(result) == 3
    assert result["taxon"].iloc[0] == "Nucella ostrina"
    assert result["mass_g"].iloc[0] == pytest.approx(0.7)
    assert result["source"].iloc[0] == "Novak_unpubl"
    assert result["mass_g"].iloc[1] > 0
    assert result["source"].iloc[1].startswith("tbmML_")
    assert math.isnan(result["mass_g"].iloc[2])
    assert result["source"].iloc[2] is None


# ---------------------------------------------------------------------------
# lookup parameter
# ---------------------------------------------------------------------------


@skip_without_artifacts
def test_lookup_false_routes_dict_species_through_model():
    """With lookup=False, a dict species should get model mass, not empirical."""
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Nucella ostrina", lookup=False)
    assert result["mass_g"].iloc[0] != pytest.approx(0.7)


@skip_without_artifacts
def test_lookup_false_include_source_returns_tbmml_prefix():
    import taxonbodymassml as tbm

    result = tbm.predict_mass("Nucella ostrina", lookup=False, include_source=True)
    assert result["source"].iloc[0].startswith("tbmML_")


# ---------------------------------------------------------------------------
# Golden predictions: the XGBoost method must reproduce the training model
# exactly (guards against column-order, encoding and xgboost-version drift).
# ---------------------------------------------------------------------------
_GOLDEN = (
    __import__("pathlib").Path(__file__).resolve().parents[3]
    / "predictive_models"
    / "results"
    / "golden_predictions.json"
)


@skip_without_artifacts
@pytest.mark.skipif(not _GOLDEN.exists(), reason="golden_predictions.json not in this checkout")
@pytest.mark.parametrize(
    "method,key", [("XGBoost", "log10_mass_g"), ("EntityEmbeddings", "log10_mass_g_ee")]
)
def test_matches_golden_predictions(method, key):
    import json

    import numpy as np
    import taxonbodymassml as tbm

    cases = json.loads(_GOLDEN.read_text())["cases"]
    if not all(key in c for c in cases):
        pytest.skip(f"golden file has no {key}")
    cols = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
    df = pd.DataFrame(cases)[cols].rename(columns={"species": "species_resolved"})
    out = tbm.predict_mass(df, method=method, lookup=False)
    got = np.log10(out["mass_g"].to_numpy())
    expected = np.array([c[key] for c in cases])
    assert np.max(np.abs(got - expected)) < 1e-5
