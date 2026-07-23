"""
Tests for taxonbodymassml.lookup_taxonomy().

Network tests are skipped unless TAXONBODYMASSML_RUN_INTEGRATION=1.
"""

import os

import pytest

INTEGRATION = os.environ.get("TAXONBODYMASSML_RUN_INTEGRATION", "0") == "1"
skip_without_network = pytest.mark.skipif(
    not INTEGRATION, reason="Requires network; set TAXONBODYMASSML_RUN_INTEGRATION=1"
)


def test_tbm_options_invalid():
    from taxonbodymassml._lookup import tbm_options

    with pytest.raises(ValueError, match="Unknown option"):
        tbm_options(not_an_option=True)


def test_normalise():
    from taxonbodymassml._lookup import _normalise

    assert _normalise("Mus_musculus") == "mus musculus"
    assert _normalise("  Mus musculus  ") == "mus musculus"


def test_parse_ncbi_xml():
    from taxonbodymassml._lookup import _parse_ncbi_xml

    xml = """<TaxaSet><Taxon>
      <ScientificName>Mus musculus</ScientificName>
      <LineageEx>
        <Taxon><Rank>kingdom</Rank><ScientificName>Metazoa</ScientificName></Taxon>
        <Taxon><Rank>phylum</Rank><ScientificName>Chordata</ScientificName></Taxon>
        <Taxon><Rank>class</Rank><ScientificName>Mammalia</ScientificName></Taxon>
      </LineageEx>
    </Taxon></TaxaSet>"""
    result = _parse_ncbi_xml(xml)
    assert result["species"] == "Mus musculus"
    assert result["kingdom"] == "Metazoa"
    assert result["phylum"] == "Chordata"
    assert result["class"] == "Mammalia"


def test_parse_ncbi_xml_malformed():
    from taxonbodymassml._lookup import _parse_ncbi_xml

    result = _parse_ncbi_xml("not valid xml <<<")
    assert result == {}


@skip_without_network
def test_lookup_known_species():
    import taxonbodymassml as tbm

    result = tbm.lookup_taxonomy("Mus musculus")
    assert result["kingdom"].iloc[0] in {"Animalia", "Metazoa"}
    assert result["species_resolved"].iloc[0] is not None


@skip_without_network
def test_lookup_list():
    import taxonbodymassml as tbm

    result = tbm.lookup_taxonomy(["Mus musculus", "Panthera leo"])
    assert len(result) == 2
    assert set(result["kingdom"]) <= {"Animalia", "Metazoa"}


@skip_without_network
def test_lookup_unresolvable():
    import warnings
    import taxonbodymassml as tbm

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        result = tbm.lookup_taxonomy("xxxxnotaspeciesxxxx")
    assert any("Could not resolve" in str(warning.message) for warning in w)
    assert result["species_resolved"].iloc[0] is None


@skip_without_network
def test_session_cache_hit():
    import taxonbodymassml as tbm
    from taxonbodymassml._lookup import _SESSION_CACHE, _normalise

    tbm.tbm_clear_cache(disk=False, session=True)
    tbm.lookup_taxonomy("Mus musculus")
    assert _normalise("Mus musculus") in _SESSION_CACHE


@skip_without_network
def test_get_citations_path():
    import taxonbodymassml as tbm

    path = tbm.get_citations()
    assert path.exists()
    assert path.suffix == ".bib"
