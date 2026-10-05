"""
Tests for taxonbodymassml.get_citations() and create_bib().

None of these need network access or the model artifacts: they use the
bundled CSV/bib and small inline fixtures.
"""

import warnings

import pytest

MINI_BIB = "\n".join(
    [
        "%% This BibTeX bibliography file was created using BibDesk.",
        "",
        "@article{Smith-Jones:2020aa,",
        "\tauthor = {Smith, A and Jones, B{\\'e}n},",
        "\ttitle = {A {Nested} {{Title}}},",
        "\tyear = {2020}}",
        "",
        "@book{Smith-Jones:2020ab,",
        "\ttitle = {Other},",
        "\tyear = {2021}}",
        "",
    ]
)


def test_bundled_files_exist():
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _citeid_path

    assert tbm.get_citations().exists()
    assert tbm.get_citations().suffix == ".bib"
    assert _citeid_path().exists()
    assert _citeid_path().suffix == ".csv"


def test_normalise_label():
    from taxonbodymassml._citations import _normalise_label

    assert _normalise_label("Martinez‐Palacios_1992") == "Martinez-Palacios_1992"
    assert _normalise_label("Cervigón_1992") == "Cervigon_1992"
    assert _normalise_label("Galván-Villa_2021") == "Galvan-Villa_2021"
    assert _normalise_label("Aydın_2018") == "Aydin_2018"
    assert _normalise_label(" fishbase ") == "fishbase"
    assert _normalise_label("Meiri_2018") == "Meiri_2018"


def test_split_sources():
    from taxonbodymassml._citations import _split_sources

    values = [
        "Novak_unpubl",
        "Feldman_etal_2016; Meiri_2018",
        "tbmML_genus",
        "tbmML_UNK",
        None,
        float("nan"),
        "",
        " Meiri_2018 ",
    ]
    assert _split_sources(values) == ["Novak_unpubl", "Feldman_etal_2016", "Meiri_2018"]
    assert _split_sources([None, "tbmML_family"]) == []


def test_extract_bib_entry_verbatim_and_exact_key():
    from taxonbodymassml._citations import _extract_bib_entry

    entry = _extract_bib_entry(MINI_BIB, "Smith-Jones:2020aa")
    assert entry.startswith("@article{Smith-Jones:2020aa,")
    assert entry.endswith("{{Title}}},\n\tyear = {2020}}")
    assert "Other" not in entry

    last = _extract_bib_entry(MINI_BIB, "Smith-Jones:2020ab")
    assert last.startswith("@book{Smith-Jones:2020ab,")
    assert last.endswith("{2021}}")

    assert _extract_bib_entry(MINI_BIB, "Smith-Jones:2020a") is None
    assert _extract_bib_entry(MINI_BIB, "Nobody:9999aa") is None


def test_read_citeids():
    from taxonbodymassml._citations import _read_citeids

    mapping = _read_citeids()
    assert mapping["Meiri_2018"] == "Meiri:2018aa"
    assert "" not in mapping
    assert "NA" not in mapping


def test_every_mapped_bibcite_is_in_bundled_bib():
    """Keys of the CiteID map that belong to the compilation bibliography
    (`bib_file == "Citations"`; the primary CiteIDs point at the primary bib,
    checked in test_primary_citeids_are_in_the_primary_bib) are all present."""
    import pandas as pd
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _citeid_path, _extract_bib_entry, _read_citeids

    cite = pd.read_csv(_citeid_path(), dtype=str, keep_default_na=False)
    assert list(cite.columns[:2]) == ["Bibcite", "CiteID"]  # the readers use these only
    primary_keys = set(cite.loc[cite.get("bib_file", "") == "PrimaryCitations", "Bibcite"])
    bibtext = tbm.get_citations().read_text(encoding="utf-8")
    mapped = set(_read_citeids().values())
    missing = [k for k in mapped - primary_keys if _extract_bib_entry(bibtext, k) is None]
    assert missing == []
    assert primary_keys  # the DB side ships primary CiteIDs
    assert all(_extract_bib_entry(bibtext, k) is None for k in primary_keys)  # not duplicated


def test_create_bib_writes_mapped_entries(tmp_path):
    import pandas as pd
    import taxonbodymassml as tbm

    x = pd.DataFrame(
        {
            "taxon": ["a", "b", "c", "d"],
            "mass_g": [1.0, 2.0, 3.0, float("nan")],
            "source": ["Nobody_9999", "Feldman_etal_2016; Meiri_2018", "tbmML_genus", None],
        }
    )
    out_file = tmp_path / "sources.bib"
    with pytest.warns(UserWarning, match="Nobody_9999"):
        out = tbm.create_bib(x, out_file)
    assert out == out_file.resolve()

    text = out.read_text(encoding="utf-8")
    first = text.splitlines()[0]
    assert first == "%% TaxonBodyMassML create_bib(): 2 data-source citation(s) for 4 taxa"
    assert "\n@article{Feldman:2016aa," in text
    assert "\n@article{Meiri:2018aa," in text
    assert "tbmML" not in text
    assert "Nobody" not in text


def test_create_bib_matches_dash_and_accent_variants(tmp_path):
    import warnings

    import pandas as pd
    import taxonbodymassml as tbm

    x = pd.DataFrame({"source": ["Martinez‐Palacios_1992", "Cervigón_1992"]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = tbm.create_bib(x, tmp_path / "s.bib")
    text = out.read_text(encoding="utf-8")
    assert "{Martinez-Palacios:1992aa," in text
    assert "{Cervigon:1992aa," in text


def test_create_bib_model_only_rows_gives_empty_bib(tmp_path):
    import warnings

    import pandas as pd
    import taxonbodymassml as tbm

    x = pd.DataFrame({"source": ["tbmML_genus", "tbmML_UNK", None]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = tbm.create_bib(x, tmp_path / "s.bib")
    text = out.read_text(encoding="utf-8")
    assert "0 data-source citation(s) for 3 taxa" in text
    assert "@" not in text


def test_create_bib_default_filename(tmp_path, monkeypatch):
    import pandas as pd
    import taxonbodymassml as tbm

    monkeypatch.chdir(tmp_path)
    out = tbm.create_bib(pd.DataFrame({"source": ["Meiri_2018"]}))
    assert out.name == "TaxonBodyMass_sources.bib"
    assert out.exists()


def test_create_bib_rejects_bad_input():
    import pandas as pd
    import taxonbodymassml as tbm

    with pytest.raises(ValueError, match="source"):
        tbm.create_bib(pd.DataFrame({"taxon": ["x"]}))
    with pytest.raises(ValueError, match="DataFrame"):
        tbm.create_bib({"source": ["a"]})


# ---------------------------------------------------------------------------
# Citation levels (TaxonBodyMass_DB issue #1 / TaxonBodyMassML #21).  The
# provenance table and the primary bibliography are model artifacts; the tests
# point the package at offline fixtures copied from TaxonBodyMass_DB (every
# accepted row of the provenance table plus a few conversion, self, pending,
# uningested and unreferenced rows).
# ---------------------------------------------------------------------------
_FIXTURES = __import__("pathlib").Path(__file__).resolve().parent / "data"
_REPO_DATA = __import__("pathlib").Path(__file__).resolve().parents[3] / "data"
_ACCEPTED = {"certain", "approved", "nodoi_approved"}


@pytest.fixture
def offline_provenance(monkeypatch):
    """Serve the fixture provenance table and primary bib instead of the artifact cache."""
    from taxonbodymassml import _citations

    monkeypatch.setattr(
        _citations, "_primary_bib_path", lambda: _FIXTURES / "PrimaryCitations_BodyMass.bib"
    )
    monkeypatch.setattr(
        _citations, "_provenance_path", lambda: _FIXTURES / "provenance_subset.csv.gz"
    )
    return _citations


def _keys_in(text: str) -> list[str]:
    import re

    return re.findall(r"^@[A-Za-z]+\{([^,]+),", text, re.MULTILINE)


def test_primary_citeids_are_in_the_primary_bib(offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _citeid_path, _extract_bib_entry

    cite = pd.read_csv(_citeid_path(), dtype=str, keep_default_na=False)
    prim_bib = tbm.get_citations("primary").read_text(encoding="utf-8")
    keys = cite.loc[cite["bib_file"] == "PrimaryCitations", "Bibcite"]
    assert set(cite["role"]) == {"source", "conversion", "primary"}
    assert [k for k in keys if _extract_bib_entry(prim_bib, k) is None] == []


def test_get_citations_levels(offline_provenance):
    import taxonbodymassml as tbm

    src = tbm.get_citations()
    assert src == tbm.get_citations("source")
    assert src.name == "Citations_BodyMass.bib"
    prim = tbm.get_citations("primary")
    assert prim.name == "PrimaryCitations_BodyMass.bib"
    assert prim.read_text(encoding="utf-8").startswith("%% GENERATED")
    both = tbm.get_citations("all")
    assert isinstance(both, tuple) and both == (src, prim)


def test_invalid_level_raises(offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm

    with pytest.raises(ValueError, match="level"):
        tbm.get_citations("secondary")
    with pytest.raises(ValueError, match="level"):
        tbm.create_bib(pd.DataFrame({"source": ["Meiri_2018"]}), level="Primary")
    with pytest.raises(ValueError, match="level"):
        tbm.create_bib(pd.DataFrame({"source": ["Meiri_2018"]}), level=None)


def test_read_provenance_types(offline_provenance):
    from taxonbodymassml._citations import _PROVENANCE_COLS, _read_provenance

    prov = _read_provenance()
    assert list(prov.columns) == _PROVENANCE_COLS
    assert prov["hop"].dtype.kind == "i" and prov["n_records"].dtype.kind == "i"
    assert prov["match_status"].isna().any()  # literal "NA" is read as missing
    assert "NA" not in set(prov["primary_bibcite"].dropna())
    assert (prov["hop"] >= 0).all() and (prov["n_records"] >= 1).all()


def _accepted_bibcites_present_in_a_bib(prov, src_bib, prim_bib):
    from taxonbodymassml._citations import _extract_bib_entry

    acc = prov[
        prov["match_status"].isin(_ACCEPTED) | (prov["provenance_type"] == "conversion_factor")
    ]
    keys = sorted(set(acc["primary_bibcite"].dropna()))
    assert keys, "fixture has no accepted primary references"
    return [
        k
        for k in keys
        if _extract_bib_entry(prim_bib, k) is None and _extract_bib_entry(src_bib, k) is None
    ]


def test_every_accepted_primary_bibcite_is_in_one_of_the_bibs(offline_provenance):
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _read_provenance

    src_bib = tbm.get_citations("source").read_text(encoding="utf-8")
    prim_bib = tbm.get_citations("primary").read_text(encoding="utf-8")
    assert _accepted_bibcites_present_in_a_bib(_read_provenance(), src_bib, prim_bib) == []


@pytest.mark.skipif(
    not (_REPO_DATA / "TaxonBodyMass_Provenance.csv.gz").exists(),
    reason="full provenance table not in this checkout (run scripts/fetch_source_data.py)",
)
def test_full_provenance_table_matches_the_bibs():
    """The staged artifacts (data/) agree with each other and with the bundled bib."""
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _read_provenance

    prov = _read_provenance(_REPO_DATA / "TaxonBodyMass_Provenance.csv.gz")
    src_bib = tbm.get_citations("source").read_text(encoding="utf-8")
    prim_bib = (_REPO_DATA / "PrimaryCitations_BodyMass.bib").read_text(encoding="utf-8")
    assert _accepted_bibcites_present_in_a_bib(prov, src_bib, prim_bib) == []
    # no key may be in both bibliographies (TaxonBodyMass_DB CheckBibKeysUnique)
    assert set(_keys_in(src_bib)) & set(_keys_in(prim_bib)) == set()


def test_create_bib_primary_from_first_accepted_provenance_row(tmp_path, offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _read_provenance

    prov = _read_provenance()
    row = prov[prov["match_status"].isin(_ACCEPTED)].iloc[0]
    x = pd.DataFrame(
        {
            "taxon": [row["species"]],
            "mass_g": [1.0],
            "source": [row["source_mass"]],
            "source_taxon": [row["species"]],
        }
    )
    out = tbm.create_bib(x, tmp_path / "p.bib", level="primary")
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0].endswith("primary-reference citation(s) for 1 taxa")
    assert row["primary_bibcite"] in _keys_in(text)
    # the compilation itself is not cited at level="primary"
    assert row["source_bibcite"] not in _keys_in(text)


def test_create_bib_primary_first_provenance_row_has_no_primary_yet(tmp_path, offline_provenance):
    """The first row of the table (Abacoproeces saltuum, derived_allometry, unresolved)."""
    import pandas as pd
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _read_provenance

    row = _read_provenance().iloc[0]
    assert row["hop"] >= 1 and row["match_status"] not in _ACCEPTED
    x = pd.DataFrame({"source": [row["source_mass"]], "source_taxon": [row["species"]]})
    with pytest.warns(UserWarning, match="not yet resolved"):
        out = tbm.create_bib(x, tmp_path / "p.bib", level="primary")
    text = out.read_text(encoding="utf-8")
    assert text.splitlines()[0].startswith(
        "%% TaxonBodyMassML create_bib(): 0 primary-reference citation(s) for 1 taxa"
    )
    assert _keys_in(text) == []


def test_create_bib_primary_includes_conversion_factor_rows(tmp_path, offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _read_provenance

    prov = _read_provenance()
    conv = prov[prov["provenance_type"] == "conversion_factor"]
    sp = conv["species"].iloc[0]
    expected = set(conv.loc[conv["species"] == sp, "primary_bibcite"])
    x = pd.DataFrame({"source": [conv["source_mass"].iloc[0]], "source_taxon": [sp]})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # other rows of the species may be unresolved
        out = tbm.create_bib(x, tmp_path / "c.bib", level="primary")
    assert expected <= set(_keys_in(out.read_text(encoding="utf-8")))


def test_create_bib_all_is_union_without_duplicate_keys(tmp_path, offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _read_provenance

    prov = _read_provenance()
    acc = prov[prov["match_status"].isin(_ACCEPTED)]
    conv = prov[prov["provenance_type"] == "conversion_factor"]
    # Kiorboe_2013 is a data source (source level) and a conversion-factor
    # reference of other sources (primary level): the key must appear once.
    kiorboe_src = acc[acc["source_mass"] == "Kiorboe_2013"].iloc[0]
    kiorboe_conv = conv[conv["primary_cite_id"] == "Kiorboe_2013"].iloc[0]
    x = pd.DataFrame(
        {
            "taxon": [kiorboe_src["species"], kiorboe_conv["species"], "Nucella lima"],
            "source": [kiorboe_src["source_mass"], kiorboe_conv["source_mass"], "tbmML_genus"],
            "source_taxon": [kiorboe_src["species"], kiorboe_conv["species"], None],
        }
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = tbm.create_bib(x, tmp_path / "all.bib", level="all")
    text = out.read_text(encoding="utf-8")
    keys = _keys_in(text)
    assert len(keys) == len(set(keys))
    assert keys.count("Kiorboe:2013aa") == 1
    assert kiorboe_src["primary_bibcite"] in keys  # primary reference of the Kiorboe species
    assert kiorboe_conv["source_bibcite"] in keys  # the data source of the other species
    header = text.splitlines()[0]
    assert "data-source and" in header and "primary-reference citation(s)" in header
    assert f"({len(keys)} unique) for 3 taxa" in header


def test_create_bib_primary_join_fallbacks(tmp_path, offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _read_provenance

    prov = _read_provenance()
    row = prov[prov["match_status"].isin(_ACCEPTED)].iloc[0]
    # species_resolved is used when source_taxon is absent (no warning about the join)
    x = pd.DataFrame({"source": [row["source_mass"]], "species_resolved": [row["species"]]})
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        out = tbm.create_bib(x, tmp_path / "a.bib", level="primary")
    assert not any("joining the provenance table on `taxon`" in str(i.message) for i in w)
    assert row["primary_bibcite"] in _keys_in(out.read_text(encoding="utf-8"))
    # taxon is the last resort and warns
    x = pd.DataFrame({"taxon": [row["species"]], "source": [row["source_mass"]]})
    with pytest.warns(UserWarning, match="joining the provenance table on `taxon`"):
        out = tbm.create_bib(x, tmp_path / "b.bib", level="primary")
    assert row["primary_bibcite"] in _keys_in(out.read_text(encoding="utf-8"))


def test_create_bib_primary_warns_on_species_absent_from_table(tmp_path, offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm

    x = pd.DataFrame({"source": ["Meiri_2018"], "source_taxon": ["Zzzz notaspecies"]})
    with pytest.warns(UserWarning, match="absent from the provenance table"):
        out = tbm.create_bib(x, tmp_path / "x.bib", level="primary")
    assert _keys_in(out.read_text(encoding="utf-8")) == []


def test_create_bib_primary_model_rows_only_touch_nothing(tmp_path, offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm

    x = pd.DataFrame({"source": ["tbmML_genus", None], "source_taxon": [None, None]})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = tbm.create_bib(x, tmp_path / "m.bib", level="all")
    text = out.read_text(encoding="utf-8")
    assert "0 data-source and 0 primary-reference citation(s) (0 unique) for 2 taxa" in text
    assert "@" not in text


def test_source_level_output_is_unchanged_by_level_argument(tmp_path, offline_provenance):
    import pandas as pd
    import taxonbodymassml as tbm

    x = pd.DataFrame({"source": ["Meiri_2018"], "source_taxon": ["Anolis carolinensis"]})
    a = tbm.create_bib(x, tmp_path / "a.bib").read_text(encoding="utf-8")
    b = tbm.create_bib(x, tmp_path / "b.bib", level="source").read_text(encoding="utf-8")
    assert a == b
    assert (
        a.splitlines()[0] == "%% TaxonBodyMassML create_bib(): 1 data-source citation(s) for 1 taxa"
    )
