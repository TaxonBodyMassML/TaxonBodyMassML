"""
Tests for taxonbodymassml.get_citations() and create_bib().

None of these need network access or the model artifacts: they use the
bundled CSV/bib and small inline fixtures.
"""

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
    import taxonbodymassml as tbm
    from taxonbodymassml._citations import _extract_bib_entry, _read_citeids

    bibtext = tbm.get_citations().read_text(encoding="utf-8")
    missing = [k for k in set(_read_citeids().values()) if _extract_bib_entry(bibtext, k) is None]
    assert missing == []


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
