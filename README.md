# TaxonBodyMassML - Taxonomy-informed prediction of species body mass 

Body mass is a powerful trait because it scales predictably with many aspects of a species’ biology.  Species with larger body mass generally have a lower metabolic rate (per unit mass), a longer generation time, and greater resource requirements.  Body mass correlates with a species' life‑history traits—such as dispersal distance, reproductive output, and lifespan—and influences its interactions with other species, including its predator-prey relationships and competitive abilities.  Body mass is thus central to predicting population dynamics and community structure, and serves as a practical, integrative metric for understanding species’ responses to environmental change.  

Unfortunately, although the body mass of thousands of species has been measured, these represent only a tiny fraction of all scientifically-described species.  `TaxonBodyMassML` provides a solution to predict the body mass of unmeasured species (and measured species) along with associated estimates of uncertainty.

`TaxonBodyMassML` is based on a comprehensive database of measured species body masses that was used to train a machine learning model to estimate a species' body mass from its scientific name and taxonomy.  The model is integrated into an [open web interface](https://taxonbodymassml.github.io) and both R and Python packages.   All three allow for single- and batch querying of species scientific names.


## Packages

The pre-trained XGBoost model (~2 GB) is automatically downloaded from [Hugging Face](https://huggingface.co/marknovak/TaxonBodyMassML) on first use of the packages; internet access is also required for taxonomy lookups via the [GBIF](https://www.gbif.org/) fuzzy-match API and the [NCBI Taxonomy database](https://www.ncbi.nlm.nih.gov/taxonomy/).

### R

```r
# install.packages("pak")
pak::pkg_install("url::https://github.com/TaxonBodyMassML/TaxonBodyMassML/releases/download/r-v0.5.0/TaxonBodyMassML_0.5.0.tar.gz")
```

See the [Getting Started vignette](packages/r/vignettes/getting-started.Rmd) for full usage including confidence intervals, taxonomy lookup, disk caching, and citation instructions.

### Python

```bash
pip install "https://github.com/TaxonBodyMassML/TaxonBodyMassML/releases/download/python-v0.5.0/taxonbodymassml-0.5.0-py3-none-any.whl"
```

See the [Python package readme](packages/python/README.md) for the full API reference.

## Data Sources
Training data sources are listed in [data/Citations_BodyMass.bib](data/Citations_BodyMass.bib), including the [FracFeed: Global database of the fraction of feeding predators](https://github.com/marknovak/FracFeed_DB), which motivated the compilation of the body mass data.

---
---