# Data

All files here are copies of, or derived from, the
[TaxonBodyMass_DB](https://github.com/TaxonBodyMassML/TaxonBodyMass_DB)
repository, which is the single source of truth for the compiled body-mass
database (parsing of each source, name cleaning, taxonomic enrichment through
GBIF, NCBI, WoRMS, Catalogue of Life, ITIS and Wikidata, autotroph removal and
deduplication all happen there). `make data/TaxonBodyMass.csv` in the
repository root runs `scripts/fetch_source_data.py`, which copies the current
database outputs into this directory.

## Fetched from TaxonBodyMass_DB

**`TaxonBodyMass.csv`** — one row per accepted species with its body mass in
grams, full kingdom-to-genus classification and provenance. Columns: `genus`,
`species`, `taxon`, `taxon_provided`, `log10_range`, `mass_g`, `source_mass`,
`n`, `kingdom`, `phylum`, `class`, `order`, `family`, `taxonomy_source`,
`gbif_confidence`, `gbif_status`, `gbif_family`, `gbif_order`,
`species_changed`. `source_mass` lists the contributing sources (`;`-separated)
and `n` the number of source records averaged. This file also feeds
`artifacts/lookup.json`, the species-to-mass dictionary the packages consult
before calling a model.

**`Citations_BodyMass.bib`** — BibTeX references for every body-mass data
source (the manuscript's "number of sources" is the number of entries).

**`TaxonBodyMass_CitationCiteIDs.csv`** — maps `source_mass` labels to BibTeX
keys.

## Derived here

**`split/train.csv`** / **`split/test.csv`** — random 90/10 split
(`data_partition/data_split_visualization.py`, seed 42) of the rows with a
complete kingdom-to-genus classification. Columns: `genus`, `species`,
`mass_g`, `kingdom`, `phylum`, `class`, `order`, `family`. Both models are
trained on `kingdom` .. `genus` from `train.csv`; `species` is not a feature
(see `predictive_models/taxonomy_encoding.py`). Test species never occur in
the training split.
