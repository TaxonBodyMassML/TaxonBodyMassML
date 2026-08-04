# taxonbodymassml

Predict species body mass from taxonomic identity using the TaxonBodyMassML XGBoost model.

## Installation

```bash
pip install "https://github.com/TaxonBodyMassML/TaxonBodyMassML/releases/download/python-v0.5.0/taxonbodymassml-0.5.0-py3-none-any.whl"
```

Optional progress bars:

```bash
pip install "taxonbodymassml[progress]"
```

## Quick start

```python
import taxonbodymassml as tbm

# Single species — model artifacts are downloaded automatically on first use (~2 GB, once only)
tbm.predict_mass("Haustrum scobina")
#   taxon     mass_g
# 0  Haustrum scobina  0.382...

# Multiple species with 90% conformal prediction interval
tbm.predict_mass(["Haustrum scobina", "Mus musculus"], confidence_interval=True)

# Custom interval level
tbm.predict_mass("Panthera leo", confidence_interval=0.80)

# Include resolved taxonomy in output
tbm.predict_mass("Panthera leo", include_taxonomy=True)

# Skip taxonomy lookup by passing a pre-resolved DataFrame
tax = tbm.lookup_taxonomy("Mus musculus")
tbm.predict_mass(tax)
```

## API

### `predict_mass(species, confidence_interval=False, method="XGBoost", include_taxonomy=False, fuzzy_match_name=False)`

Predict body mass for one or more species.

| Parameter | Type | Description |
|---|---|---|
| `species` | `str`, `list[str]`, or `pd.DataFrame` | Scientific name(s). Pass a DataFrame with resolved taxonomy columns to skip the GBIF/NCBI lookup. |
| `confidence_interval` | `bool` or `float` | `False`: no interval. `True`: 90% conformal interval. Float in (0, 1): interval at that coverage level. |
| `method` | `str` | `"XGBoost"` (default). Extensible for future models. |
| `include_taxonomy` | `bool` | Append resolved taxonomy columns to the output. |
| `fuzzy_match_name` | `bool` | If `True`, correct species names via the GBIF species-match API before lookup, tolerating misspellings and name variants. Appends a `matched_name` column: the originally entered name when a correction was applied or no match was found; `None` when the name was already canonical. Default `False` (exact matching). Ignored when `species` is a `pd.DataFrame`. |

Returns a `pd.DataFrame` with columns `taxon`, `mass_g` (grams), and optionally `lower_bound`, `upper_bound`, `confidence`, `kingdom` … `species_resolved`, `matched_name`.

Species that cannot be resolved to taxonomy emit a warning and return `NaN`.

> **Note:** `fuzzy_predict_mass()` is deprecated as of v0.2.1. Replace any calls to it with `predict_mass(..., fuzzy_match_name=True)`.

### `lookup_taxonomy(species)`

Resolve scientific names to 7-rank taxonomy (kingdom → species) using the GBIF fuzzy-match API with an NCBI Entrez fallback. Results are cached in-memory for the session.

### `download_model(version="latest", force=False)`

Download model artifacts from Hugging Face Hub to the local cache directory. Called automatically when needed by `predict_mass()`.

### `get_citations()`

Return the path to the bundled `Citations_BodyMass.bib` BibTeX file. Pass it to `bibtexparser.load()` or open it in Zotero, BibDesk, or JabRef.

```python
path = tbm.get_citations()
# /path/to/taxonbodymassml/data/Citations_BodyMass.bib
```

### `tbm_options(**kwargs)`

Configure package behaviour:

| Option | Default | Description |
|---|---|---|
| `disk_cache` | `False` | Persist resolved taxonomy to disk across sessions. |
| `progress` | `True` | Show a tqdm progress bar when looking up > 10 species (requires `tqdm`). |

### `tbm_clear_cache(disk=True, session=True)`

Clear the taxonomy cache (in-memory and/or on-disk).

## API compliance

### NCBI User-Agent

NCBI's terms of service require identifying the calling application. Set your contact email:

```bash
export TAXONBODYMASSML_EMAIL="your@email.com"
```

This is appended to the `User-Agent` header sent with every NCBI request:
`TaxonBodyMassML/0.2.3 (contact: your@email.com)`.

### NCBI API key

Without a key, NCBI allows 3 requests/second. With a free API key, the limit rises to 10/s. Obtain a key at <https://www.ncbi.nlm.nih.gov/account/> and set:

```bash
export NCBI_API_KEY="your_key_here"
```

The key is appended automatically to every NCBI request and the internal rate limiter adjusts accordingly.

## Data sources

Training data on each taxon's mass (in grams) was obtained from unpublished primary data,
published allometric relationships, the primary literature, and published databases.
Most mass data represent mean adult wet mass. Published mass data came from
Meiri (2018), Oliveira et al. (2017), Brown et al. (2018), Smith et al. (2003),
Anderson et al. (2017), Gillooly et al. (2016), Jennings et al. (2002),
Lislevand et al. (2007), Killen et al. (2016), Feldman et al. (2016),
Tucker et al. (2014a, b), Hirt et al. (2017), Eklöf et al. (2017), Cai et al. (2025),
Animal Diversity Web, AnAge (Tacutu et al., 2013), FishBase (Froese and Pauly, 2025),
SeaLifeBase (Palomares and Pauly, 2025), and DataRetriever (McGlinn et al., 2017).

Full formatted references and a complete per-measurement BibTeX bibliography are
available via `get_citations()` and at <https://taxonbodymassml.github.io/citations.html>.

### Selected references

Anderson, D. M. and J. F. Gillooly (2017). Physiological constraints on long-term population cycles. *Evolutionary Ecology Research*, 18(6), 693–707.

Brown, J. H., C. A. S. Hall, and R. M. Sibly (2018). Equal fitness paradigm explained by a trade-off between generation time and energy production rate. *Nature Ecology & Evolution*, 2(2), 262–268.

Cai, T., et al. (2025). Distinct latitudinal patterns of molecular rates across vertebrates. *PNAS*, 122(19):e2423386122.

Eklöf, J., et al. (2017). Size matters: relationships between body size and body mass of common coastal, aquatic invertebrates in the Baltic Sea. *PeerJ*, 5, e2906.

Feldman, A., et al. (2016). Body sizes and diversification rates of lizards, snakes, amphisbaenians and the tuatara. *Global Ecology and Biogeography*, 25(2):187–197.

Froese, R. and D. Pauly (2025). FishBase. www.fishbase.org.

Froese, R., J. T. Thorson, and R. B. Reyes Jr. (2014). A Bayesian approach for estimating length-weight relationships in fishes. *Journal of Applied Ichthyology*, 30(1), 78–85.

Gillooly, J. F., et al. (2016). Body mass scaling of passive oxygen diffusion in endotherms and ectotherms. *PNAS*, 113(19):5340–5345.

Hirt, M. R., et al. (2017). A general scaling law reveals why the largest animals are not the fastest. *Nature Ecology & Evolution*, 1(8), 1116–1122.

Jennings, S., et al. (2002). Linking size-based and trophic analyses of benthic community structure. *Marine Ecology Progress Series*, 226, 77–85.

Killen, S. S., et al. (2016). Ecological Influences and Morphological Correlates of Resting and Maximal Metabolic Rates across Teleost Fish Species. *American Naturalist*, 187(5), 592–606.

Lislevand, T., J. Figuerola and T. Székely (2007). Avian body sizes in relation to fecundity, mating system, display behavior, and resource sharing. *Ecology*, 88(6), 1605–1605.

McGlinn, D., et al. (2017). rdataretriever: R Interface to the Data Retriever. R package version 1.0.0.

Meiri, S. (2018). Traits of lizards of the world: Variation around a successful evolutionary design. *Global Ecology and Biogeography*, 27(10), 1168–1172.

Oliveira, B. F., et al. (2017). AmphiBIO, a global database for amphibian ecological traits. *Scientific Data*, 4(1):170123.

Palomares, M. L. D. and D. Pauly (2025). SeaLifeBase. www.sealifebase.org.

Smith, F. A., et al. (2003). Body mass of late quaternary mammals (v.10.2). *Ecology*, 84(12), 3403–3403.

Tacutu, R., et al. (2013). Human Ageing Genomic Resources: Integrated databases and tools for the biology and genetics of ageing. *Nucleic Acids Research*, 41(D1):D1027–D1033.

Tucker, M. A. and T. L. Rogers (2014a). Examining predator–prey body size, trophic level and body mass across marine and terrestrial mammals. *Proceedings of the Royal Society B*, 281(1797).

Tucker, M. A., T. J. Ord, and T. L. Rogers (2014b). Evolutionary predictors of mammalian home range size: body mass, diet and the environment. *Global Ecology and Biogeography*, 23(10), 1105–1114.

## License

MIT. See [LICENSE](../../LICENSE.md).

## Citation

A manuscript describing TaxonBodyMassML is in preparation. In the meantime, please cite the software directly using the metadata in `CITATION.cff`.
