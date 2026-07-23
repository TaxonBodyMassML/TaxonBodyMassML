"""
Tests for taxonbodymassml.predict_mass().

Tests that require model artifacts (the ~2 GB download) are skipped
unless TAXONBODYMASSML_RUN_INTEGRATION=1 is set in the environment.
"""

import os
import warnings

import pandas as pd
import pytest

INTEGRATION = os.environ.get("TAXONBODYMASSML_RUN_INTEGRATION", "0") == "1"
skip_without_artifacts = pytest.mark.skipif(
    not INTEGRATION, reason="Requires model artifacts; set TAXONBODYMASSML_RUN_INTEGRATION=1"
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

    result = tbm.predict_mass("Mus musculus", confidence_interval=True)
    assert "lower_bound" in result.columns
    assert "upper_bound" in result.columns
    assert result["confidence"].iloc[0] == pytest.approx(0.90)
    assert result["lower_bound"].iloc[0] < result["mass_g"].iloc[0]
    assert result["upper_bound"].iloc[0] > result["mass_g"].iloc[0]


@skip_without_artifacts
def test_predict_confidence_interval_custom():
    import taxonbodymassml as tbm

    r90 = tbm.predict_mass("Mus musculus", confidence_interval=0.90)
    r80 = tbm.predict_mass("Mus musculus", confidence_interval=0.80)
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
    assert any("Could not resolve" in str(warning.message) for warning in w)
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
