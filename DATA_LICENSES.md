# Data licences

> **None of this is legal advice.**

## Quick summary

| What | Licence |
|---|---|
| Code, packages, model weights | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) |
| Training data, lookup table (`lookup.json`), provenance artifacts | [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) |

**CC BY-NC 4.0** means you may share and adapt with attribution **for non-commercial purposes only**. Commercial use requires permission from the owner.

Everything in this repository — code, packages, model weights, and data artifacts — therefore carries the NonCommercial term. The data artifacts (`lookup.json`, `TaxonBodyMass_Provenance.csv.gz`, `PrimaryCitations_BodyMass.bib`, `TaxonBodyMass_Citations.bib`, and the training data) additionally derive from [TaxonBodyMass_DB](https://github.com/TaxonBodyMassML/TaxonBodyMass_DB), which is also published under CC BY-NC 4.0.

## Sources with additional restrictions

Most training sources are CC0, CC BY, or Ecological Archives data papers with no restrictions beyond attribution. However, several sources carry stricter terms, and their values appear in the lookup table and training data:

| Source | Licence | Label in results |
|---|---|---|
| FishBase, SeaLifeBase | CC BY-NC 4.0 | `fishbase`, `sealifebase` |
| Lane (2019) | CC BY-NC 4.0 | — |
| Cai et al. (2025); Hoehler et al. (2023) | CC BY-NC-ND 4.0 | — |
| Animal Diversity Web via Quaardvark | CC BY-NC-SA 3.0 | `Quaardvark` |
| Pata & Hunt (2025) | CC BY-SA 4.0 | — |
| Hechinger et al. (2011) | Non-commercial scientific use | — |

The database publishes aggregated species means (not individual measurements) under CC BY-NC 4.0. Whether your downstream use is additionally bound by the share-alike term (Pata & Hunt 2025) or the no-derivatives term (Cai et al. 2025, Hoehler et al. 2023) is for you to determine. A few sources are still listed as "unknown; owner to check" in the database.

The full per-source licence list is in TaxonBodyMass_DB: [`sources/LICENSES.md`](https://github.com/TaxonBodyMassML/TaxonBodyMass_DB/blob/main/sources/LICENSES.md).

## Identifying restricted sources in your results

To see which sources underlie each prediction, use `include_source=True` (Python) / `include_source = TRUE` (R):

```python
predict_mass(names, include_source=True)   # adds a 'source' column
```

The `source` column names the contributing source(s) for every lookup-table hit. Predictions for species **not** in the lookup table are model-only estimates and are not traceable to a single original source. The full species-level provenance is in `TaxonBodyMass_Provenance.csv.gz`.
