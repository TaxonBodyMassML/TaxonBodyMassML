# TaxonBodyMassML - Taxonomy-informed prediction of species body mass 

Body mass is a powerful trait because it scales predictably with many aspects of a species’ biology.  Species with larger body mass generally have a lower metabolic rate (per unit mass), a longer generation time, and greater resource requirements.  Body mass correlates with a species' life‑history traits—such as dispersal distance, reproductive output, and lifespan—and influences its interactions with other species, including its predator-prey relationships and competitive abilities.  Body mass is thus central to predicting population dynamics and community structure, and serves as a practical, integrative metric for understanding species’ responses to environmental change.  

Unfortunately, although the body mass of thousands of species has been measured, these represent only a tiny fraction of all scientifically-described species.  `TaxonBodyMassML` provides a solution to predict the body mass of unmeasured species (and measured species) along with associated estimates of uncertainty.

`TaxonBodyMassML` is based on a comprehensive [database](https://github.com/TaxonBodyMassML/TaxonBodyMass_DB) of measured species body masses that was used to train a machine learning model to estimate a species' body mass from its scientific name and taxonomy.  The model is integrated into an [open web interface](https://taxonbodymassml.github.io) and both R and Python packages.   All three allow for single- and batch querying of species scientific names.


## Packages

The pre-trained models (~0.4 GB in total) are automatically downloaded from [Hugging Face](https://huggingface.co/marknovak/TaxonBodyMassML) on first use of the packages; internet access is also required for taxonomy lookups via the [GBIF](https://www.gbif.org/) fuzzy-match API and the [NCBI Taxonomy database](https://www.ncbi.nlm.nih.gov/taxonomy/).

### R

```r
# install.packages("pak")
pak::pkg_install("url::https://github.com/TaxonBodyMassML/TaxonBodyMassML/releases/latest/download/TaxonBodyMassML_latest.tar.gz")
```

See the [Getting Started vignette](packages/r/vignettes/getting-started.Rmd) for full usage including confidence intervals, taxonomy lookup, disk caching, and citation instructions.

### Python

```bash
pip install "https://github.com/TaxonBodyMassML/TaxonBodyMassML/releases/latest/download/taxonbodymassml-latest-py3-none-any.whl"
```

See the [Python package readme](packages/python/README.md) for the full API reference.

## Data Sources
Training data sources are listed in [data/Citations_BodyMass.bib](data/Citations_BodyMass.bib), including the [FracFeed: Global database of the fraction of feeding predators](https://github.com/marknovak/FracFeed_DB), which motivated the compilation of the body mass data.
Both packages bundle this bibliography (`get_citations()`) and, via `create_bib()`, can write a `.bib` file containing only the sources behind a given set of `predict_mass(..., include_source = TRUE)` results.
Most sources are compilations that reproduce measurements published elsewhere. TaxonBodyMass_DB is attributing every record to the study that measured the animal ([TaxonBodyMass_DB#1](https://github.com/TaxonBodyMassML/TaxonBodyMass_DB/issues/1)); the verified primary references ship as model artifacts next to `lookup.json` ([data/PrimaryCitations_BodyMass.bib](data/PrimaryCitations_BodyMass.bib), [data/TaxonBodyMass_Provenance.csv.gz](data/TaxonBodyMass_Provenance.csv.gz)) and are returned by `get_citations(level = "primary")` and `create_bib(..., level = "primary")`. Coverage grows source by source; `create_bib()` reports the species whose primary references are not yet resolved, and the compilation remains the citation of record for them.

## Data licences

The packages, the model weights and this repository are MIT-licensed ([LICENSE.md](LICENSE.md)). The training data, the species-to-mass lookup table (`lookup.json`) and the provenance artifacts (`PrimaryCitations_BodyMass.bib`, `TaxonBodyMass_Provenance.csv.gz`) aggregate values compiled by [TaxonBodyMass_DB](https://github.com/TaxonBodyMassML/TaxonBodyMass_DB), whose own outputs (the compiled tables, the two bibliographies and the provenance table) are published under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (Creative Commons Attribution-NonCommercial 4.0 International; owner decision of 2026-10-06, replacing CC BY 4.0; earlier database releases keep the licence they carried). The data artifacts built from them, `lookup.json`, `TaxonBodyMass_Provenance.csv.gz`, `PrimaryCitations_BodyMass.bib`, `TaxonBodyMass_Citations.bib` and the training data, therefore carry the NonCommercial term: they may be shared and adapted with attribution for non-commercial purposes only, and a commercial use needs permission from the database owner. The code and the model weights are not affected and stay MIT. The sources behind the values keep their own terms, listed file by file in that repository's [`sources/LICENSES.md`](https://github.com/TaxonBodyMassML/TaxonBodyMass_DB/blob/main/sources/LICENSES.md) (TaxonBodyMass_DB issue #6). No raw source file ships with the packages or the artifacts: `scripts/fetch_source_data.py` copies only the compiled database, the citation map, the two bibliographies and the provenance table, and `lookup.json` holds one aggregated mass per species with the labels of the sources behind it. Most sources are CC0, CC BY or Ecological Archives data papers without copyright restrictions; several are published under terms that go beyond attribution, and values from them are in the lookup table and the training set: FishBase and SeaLifeBase (CC BY-NC 4.0; labels `fishbase`, `sealifebase`), Lane 2019 (CC BY-NC 4.0), Cai et al. 2025 and Hoehler et al. 2023 (CC BY-NC-ND 4.0), Animal Diversity Web through Quaardvark (CC BY-NC-SA 3.0; label `Quaardvark`), Pata & Hunt 2025 (CC BY-SA 4.0) and Hechinger et al. 2011 (non-commercial scientific use). The database treats individual body-mass values as facts and publishes the aggregated species means under CC BY-NC 4.0 as aggregated facts with attribution, which aligns the database with the non-commercial term of those sources; whether a downstream use is also bound by the share-alike (Pata & Hunt 2025) or no-derivatives (Cai et al. 2025, Hoehler et al. 2023) terms is for the user to decide. The `source` column of `predict_mass(..., include_source=True)` and the provenance artifact name the sources behind every dictionary value, so such values can be excluded; model predictions for species outside the dictionary are not traceable to a single source. The terms of a few sources are not yet stated on disk in the database and are listed there as "unknown; owner to check". None of this is legal advice.

---
---