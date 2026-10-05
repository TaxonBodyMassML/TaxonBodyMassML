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
`n`, `n_sources`, `n_independent`, `source_dependencies`, `kingdom`, `phylum`,
`class`, `order`, `family`, `taxonomy_source`, `gbif_confidence`,
`gbif_status`, `gbif_family`, `gbif_order`, `species_changed`. `source_mass`
lists the contributing sources (`;`-separated) and `n` the number of source
records averaged. The same datum often reaches the database through several
compilations (AVONET and EltonTraits both reproduce Dunning's handbook, COMBINE
reproduces Amniote/PHYLACINE/MOM, ...), so TaxonBodyMass_DB collapses such
copies before averaging across sources (TaxonBodyMass_DB#5, #49) and records
the de-duplication in three columns: `n_sources` (sources listed in
`source_mass`), `n_independent` (values left after collapsing copies; the
cross-source mean is taken over these) and `source_dependencies` (the
collapsed pairs as `dropped<kept`, `;`-separated, `NA` when nothing was
collapsed). `scripts/extract_training_stats.py` sums `n_independent` into
`nIndependentValues`; `n` (`nSourceRecords`) is duplicate-inflated. This file
also feeds `artifacts/lookup.json`, the species-to-mass dictionary the
packages consult before calling a model.

**`TaxonBodyMass_GenusLevel.csv`** (not fetched here; in TaxonBodyMass_DB) —
one row per genus (`taxon`, `mass_g`, `source_mass`, `n`, `n_independent`) for
records that could be resolved only to genus; `n_independent` has the same
meaning as above. Not used by the packages.

**`Citations_BodyMass.bib`** — BibTeX references for every body-mass data
source (the manuscript's "number of sources" is the number of entries).
Bundled by both packages (`get_citations()`).

**`TaxonBodyMass_CitationCiteIDs.csv`** — maps `source_mass` labels
(`CiteID`) to BibTeX keys (`Bibcite`). Since TaxonBodyMass_DB#1 it also carries
`doi`, `role` (`source`, `conversion` or `primary`) and `bib_file`
(`Citations` or `PrimaryCitations`, the bibliography holding the key); the
packages read the first two columns only. Bundled by both packages.

**`PrimaryCitations_BodyMass.bib`** — the generated primary-source
bibliography of TaxonBodyMass_DB (`Bib/TaxonBodyMass_PrimaryCitations.bib`;
built from Crossref metadata or owner-approved fields, never hand-edited; its
keys never overlap with `Citations_BodyMass.bib`). Not bundled: distributed as
a model artifact next to `lookup.json` and returned by
`get_citations(level = "primary")`.

**`TaxonBodyMass_Provenance.csv.gz`** — the provenance table of
TaxonBodyMass_DB (pipeline step 7): one row per species x source label x
reference for every species of `TaxonBodyMass.csv`, columns `genus`,
`species`, `taxon`, `source_mass` (one label), `source_bibcite`, `origin`,
`hop`, `via_cite_id`, `ref_role`, `provenance_type`, `primary_cite_id`,
`primary_bibcite`, `primary_doi`, `match_status`, `n_records` (see the
TaxonBodyMass_DB README for the vocabularies). `create_bib(level = "primary")`
joins the dictionary species to this table and cites the rows with
`match_status` `certain`, `approved` or `nodoi_approved` and the
`conversion_factor` rows. Not bundled: a model artifact, read by
`_read_provenance()` / `.read_provenance()`. `scripts/extract_training_stats.py`
derives `n_primary_refs`, `pct_records_hop_resolved` and `pct_records_primary`
from it.

Both provenance files must come from the same TaxonBodyMass_DB snapshot as
`lookup.json`; `scripts/fetch_source_data.py` also stages them into
`artifacts/`, `scripts/export_artifacts.py` checksums them and
`scripts/sync_checksums.py` writes the checksums into both packages
(`PROVENANCE_CHECKSUMS` / `.PROVENANCE_CHECKSUMS`). Publishing a new artifact
revision needs the owner's explicit approval.

## Derived here

**`split/train.csv`** / **`split/test.csv`** — random 90/10 split
(`data_partition/data_split_visualization.py`, seed 42) of the rows with a
complete kingdom-to-genus classification. Columns: `genus`, `species`,
`mass_g`, `kingdom`, `phylum`, `class`, `order`, `family`. Both models are
trained on `kingdom` .. `genus` from `train.csv`; `species` is not a feature
(see `predictive_models/taxonomy_encoding.py`). Test species never occur in
the training split.
