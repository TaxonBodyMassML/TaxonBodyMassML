# TaxonBodyMassML - Phylogeny-informed prediction of species body weight 

## Project Description

The project will harness a comprehensive database of measured species body masses together with the [Open Tree of Life](https://opentreeoflife.github.io/use) phylogenetic framework to train a large language model to estimate a species' body mass from its scientific name and taxonomy.  By fine‑tuning the model on thousands of name–mass pairs, it will learn how evolutionary proximity predicts body mass. The model will be integrated into an open web interface for rapid single- and batch querying of species body mass, providing ecologists with a user‑friendly tool to extrapolate to millions of unmeasured taxa.


## Motivations

Ecologists regard body mass as a master trait because it scales predictably with nearly every aspect of a species’ biology.  A larger mass generally entails a lower metabolic rate per unit volume, a longer generation time, and greater resource requirements.  It correlates with a species' life‑history traits—such as dispersal distance, reproductive output, and lifespan—and determines its interactions with other species, including its predator-prey relationships and competitive abilities.  Body mass is thus central to forecasting population dynamics and community structure, and serves as a practical, integrative metric for understanding species’ responses to environmental change.  Unfortunately, although the body mass of thousands of species has been measured, these represent only a tiny fraction of all scientifically-described species.  Tools are needed to predict the body mass of the unmeasured species.


## Objectives/Deliverables

1. A fully trained, fine‑tuned Python implementation of a large language model that ingests a species name and returns a body‑mass estimate, provenance flag, and uncertainty descriptor (e.g., whether it is a known direct measurement, an inference from a close relative, or a broader phylogenetic prediction).  
2. A clean, reproducible training pipeline (including data preprocessing, phylogenetic feature engineering, and evaluation metrics) documented in a GitHub repository.  
3. A responsive web application (frontend + backend) that accepts single or comma‑delimited species lists, queries the model, and displays and exports results with clear provenance and uncertainty.  
4. A technical report detailing model architecture, training procedure, validation results, and guidance for future extensions.  

## Data Sources
[FracFeed: Global database of the fraction of feeding predators](https://github.com/marknovak/FracFeed_DB)

[Open Tree of Life APIs](https://github.com/OpenTreeOfLife/germinator/wiki/Open-Tree-of-Life-Web-APIs)

## Organization Hosting Migration

The project is migrating to organization-owned repositories and website hosting.

1. Target organization: [TaxonBodyMassML organization](https://github.com/TaxonBodyMassML)
2. Target website URL: [taxonbodymassml.github.io](https://taxonbodymassml.github.io/)
3. Collaborator-hosted site remains unchanged and is treated as read-only source content.

Operational migration steps are documented in [documentation/ORG_MIGRATION_RUNBOOK.md](documentation/ORG_MIGRATION_RUNBOOK.md).