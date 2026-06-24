# Consolidation Parity Report

Date: 2026-06-24

## Method

1. Compared tracked files only using git ls-files in both repositories.
2. Computed set differences between:
   - /Users/novakm/Git/TaxonBodyMassML
   - /Users/novakm/Git/TaxonBodyMassMLHaileys

## Result Summary

1. Secondary-only tracked files: none.
2. Primary-only tracked files: many (data-combination, microservices, schemas, additional web assets, sprint documents).

Interpretation: TaxonBodyMassML appears to be a strict superset of TaxonBodyMassMLHaileys for tracked content.

## Consolidation Recommendation

1. Keep TaxonBodyMassML as canonical repository after org transfer.
2. Archive TaxonBodyMassMLHaileys after adding a README deprecation note that points to canonical repository.
3. Do not delete collaborator-hosted website or collaborator repositories as part of this migration.

## Primary-Only Tracked Paths (abridged)

1. data-combination/*
2. lookup_table_microservice/*
3. predictive_models/*
4. regressor_microservice/*
5. schemas/*
6. web_dev/alg.html
7. web_dev/help.js
8. web_dev/info_pages.css
9. web_dev/tutorial.css
10. web_dev/tutorial.js

## Notes

1. Full machine-generated diff artifact was created during analysis in /tmp/tbm_unique_report.txt.
2. This report is intended to support migration decisions and can be updated if repositories change.
