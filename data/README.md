# Data

## Raw data

**`BodyMass.csv`** — Raw (unprocessed) body mass data compiled from 34+ literature sources and taxonomic databases by the *TaxonBodyMass_DB* project.

GitHub repository: https://github.com/marknovak/TaxonBodyMass_DB

Columns: `taxon`, `mass_g`, `source_mass`, `n`

## Processed data

**`BodyMass_curated.csv`** — Body mass data after taxonomic enrichment through a sequential pipeline (GBIF → NCBI → WoRMS → COL ChecklistBank → Wikidata SPARQL → ITIS) and removal of non-animal eukaryotes (Plantae, Chromista, Viridiplantae, Fungi). Columns added: `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`, `confidence`, `subspecies`, `form`.

**`BodyMass_<DB>_pass.csv`** — Intermediate files from sequential taxonomic name resolution passes through each external taxonomic database (`COL`, `GBIF`, `ITIS`, `NCBI`, `Wikidata`, `WoRMS`).

**`missed_species_<DB>.txt`** — Taxa not resolved during the corresponding taxonomic name resolution pass.

**`Citations_BodyMass.bib`** — BibTeX references for the body mass data sources.

## Model data

**`train.csv`** / **`test.csv`** — Training and test splits used for the XGBoost body mass prediction model. Columns: `mass_g`, `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`.
