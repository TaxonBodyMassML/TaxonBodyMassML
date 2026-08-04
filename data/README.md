# Data

## Raw data

**`BodyMass.csv`** — Raw (unprocessed) body mass data extracted from the *FracFeed* database:

> Novak, M., Foust, P., Hennessey, S., Tanis, B. P., Coblentz, K. E., Wolf, C., Segui, L. M., Henderson, J. S., Ingeman, K. E., Falke, L. P., Layden, T. J., Gradison, D. J., Randell, Z., Harris, C. L., Lester, S., Naito, K. A., Nakata, T., Nichols, G., Postma, B. C., Alves, R., Jarman, C. N., Kalytiak-Davis, A. R., Martin, A., Pajiah, T. J., Pinos-Sánchez, A., & Preston, D. L. (2026). *FracFeed*: Global database of the fraction of feeding predators. *Ecology*, 107(1), e70296. https://doi.org/10.1002/ecy.70296

GitHub repository: https://github.com/marknovak/FracFeed_DB

Columns: `taxon`, `mass_g`, `source_mass`, `n`

## Processed data

**`BodyMass_curated.csv`** — Body mass data after taxonomic name standardization (using the Open Tree of Life via the `rotl` package), adding higher taxonomy columns (`kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`, `confidence`, `subspecies`, `form`).

**`BodyMass_<DB>_pass.csv`** — Intermediate files from sequential taxonomic name resolution passes through each external taxonomic database (`COL`, `GBIF`, `ITIS`, `NCBI`, `Wikidata`, `WoRMS`).

**`missed_species_<DB>.txt`** — Taxa not resolved during the corresponding taxonomic name resolution pass.

**`Citations_BodyMass.bib`** — BibTeX references for the body mass data sources.

## Model data

**`train.csv`** / **`test.csv`** — Training and test splits used for the XGBoost body mass prediction model. Columns: `mass_g`, `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`.
