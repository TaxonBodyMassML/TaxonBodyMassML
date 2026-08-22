# Taxonomy Enrichment Pipeline

## 1. Overview

The enrichment pipeline resolves Linnaean taxonomy for every taxon in the body-mass dataset. Starting from the raw source CSV, each pass queries a different taxonomic authority and writes only the fields still missing from the previous pass. Only rows that have at least one `NaN` field among the seven target ranks are sent to an API; rows already fully populated are left untouched.

**Target fields (all passes):** `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`

**Final output:** `data/passes/TaxonBodyMass_curated.csv` — filtered to animal taxa only.

**Missed-species logs:** each pass writes a plain-text file listing names it could not resolve (e.g. `missed_species_gbif.txt`, `missed_species_ncbi.txt`, …).

---

## 2. Source Data Import

**Script:** `scripts/fetch_source_data.py`

Copies three files from the sibling repository `TaxonBodyMass_DB` (expected at `../TaxonBodyMass_DB/` relative to the project root) into `data/`:

| Source (in TaxonBodyMass_DB) | Destination (in data/) |
|---|---|
| `TaxonBodyMass.csv` | `data/TaxonBodyMass.csv` |
| `Bib/TaxonBodyMass_Citations.csv` | `data/TaxonBodyMass_Citations.csv` |
| `Bib/TaxonBodyMass_Citations.bib` | `data/Citations_BodyMass.bib` |

The script raises `FileNotFoundError` immediately if any source is absent. Run it once before starting any enrichment pass.

---

## 3. Enrichment Passes

Passes run sequentially. Each script reads the output of the preceding pass. Only unique taxon names that still have at least one missing rank field are submitted to the API.

### Pass summary table

| # | Script | API | Input | Output | Batch / concurrency | Sleep | Checkpoint | Retry delays |
|---|---|---|---|---|---|---|---|---|
| 1 | `combination_api.py` | GBIF species/match | `TaxonBodyMass.csv` | `TaxonBodyMass_GBIF_pass.csv` | 100 rows / 8 threads | none | every 100 rows | 1 s, 2 s, 4 s |
| 2 | `ncbi_fallback.py` | NCBI Entrez (esearch + efetch) | `…_GBIF_pass.csv` | `…_NCBI_pass.csv` | 1 / sequential | 0.34 s | every 25 rows | 2 s, 5 s, 10 s |
| 3 | `worms_fallback.py` | WoRMS AphiaRecordsByMatchNames | `…_NCBI_pass.csv` | `…_WoRMS_pass.csv` | 50 names / sequential | 0.5 s | every batch (50) | none |
| 4 | `col_fallback.py` | COL ChecklistBank | `…_WoRMS_pass.csv` | `…_COL_pass.csv` | 1 / sequential | 0.5 s | every 10 names | 2 s, 5 s, 15 s |
| 5 | `wikidata_fallback.py` | Wikidata SPARQL | `…_COL_pass.csv` | `…_Wikidata_pass.csv` | 10 names / sequential | 1.0 s | every batch (10) | 5 s, 15 s, 30 s |
| 6 | `itis_fallback.py` | ITIS JSON service | `…_Wikidata_pass.csv` | `…_ITIS_pass.csv` | 1 / sequential | 0.5 s | every 10 names | 2 s, 5 s, 15 s |

All passes handle transient HTTP errors (429, 500, 502, 503, 504) with the retry delays listed above. After exhausting retries, the taxon is recorded in the missed-species log and processing continues.

---

### Pass 1 — GBIF (`combination_api.py`)

**API:** `https://api.gbif.org/v2/species/match` (fuzzy name matching)

**Fields added:** `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`, `confidence`

This is the primary and highest-volume pass. All rows in the source CSV are submitted regardless of whether taxonomy fields are already populated, because this pass also initialises the taxonomy columns.

- Uses a persistent `requests.Session` with a `User-Agent` header (`TaxonBodyMassML/<version>`, optionally including the email set in `TAXONBODYMASSML_EMAIL`).
- Work is split into chunks of 100 rows; within each chunk, 8 threads run concurrently via `ThreadPoolExecutor`.
- Results with a GBIF `confidence` score below 75 are discarded and the taxon is added to the missed list.
- Taxonomy is extracted from the `classification` array in the GBIF response; `confidence` is read from `diagnostics.confidence`.
- Checkpoint: the CSV is written after each chunk of 100 rows.

---

### Pass 2 — NCBI (`ncbi_fallback.py`)

**API:** `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/`  
Two calls per taxon: `esearch.fcgi` (retrieve Tax ID) then `efetch.fcgi` (retrieve XML lineage).

**Fields added:** any of the seven standard ranks still `NaN` after GBIF.

- Processes rows one at a time; skips rows where all seven fields are already filled.
- Parses the `LineageEx` element from NCBI's XML response to extract rank/name pairs.
- Normalises kingdom: NCBI returns "Metazoa" for animals; the script remaps this to "Animalia".
- Rate limit: `time.sleep(0.34)` after each successful lookup (~3 req/s).
- Checkpoint: writes the CSV every 25 processed rows.
- `STARTING_INDEX` constant allows resuming from an interrupted run.

---

### Pass 3 — WoRMS (`worms_fallback.py`)

**API:** `https://www.marinespecies.org/rest/AphiaRecordsByMatchNames`  
Accepts batches of up to 50 scientific names per request (`marine_only=false`).

**Fields added:** `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`

- Accepted match types: `exact`, `phonetic`, `near_1`. Records with other match types are rejected.
- Within each batch result, records with `status == "accepted"` are preferred; the first record is used as a fallback if no accepted record exists.
- Species name is taken from `scientificname` when the WoRMS record rank is "species".
- Particularly effective for marine invertebrates, fish, and other aquatic taxa.
- Checkpoint: writes the CSV after every batch of 50, then sleeps 0.5 s.

---

### Pass 4 — COL (`col_fallback.py`)

**API:** `https://api.checklistbank.org/dataset/3/nameusage/search`  
Dataset ID 3 is the Catalogue of Life checklist.

**Fields added:** `kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`

- Queries one name at a time with `rank=species&limit=5`; iterates results until a non-empty `classification` array is found.
- The queried name is assigned directly as `species` when a classification match is found.
- Particularly effective for Squamata because COL directly sources from the Reptile Database.
- Checkpoint: writes the CSV every 10 names; sleeps 0.5 s between queries.

---

### Pass 5 — Wikidata (`wikidata_fallback.py`)

**API:** `https://query.wikidata.org/sparql` (SPARQL 1.1)

**Fields added:** any of the seven standard ranks still `NaN` after COL.

- Sends batches of 10 names per SPARQL query using a `VALUES` clause.
- The query traverses the `P171*` (parent taxon, transitive) chain and retrieves `P225` (taxon name) and `P105` (taxon rank) for each ancestor, filtering for rank labels that match the seven target ranks.
- First match per rank wins within each batch result.
- Rate limit: 1.0 s sleep between batches (Wikidata's recommended maximum of 1 request/s).
- Custom `User-Agent` header is set per Wikidata's bot policy.
- Retry delays are longer than other passes (5 s, 15 s, 30 s) to respect SPARQL endpoint stability.
- Checkpoint: writes the CSV after every batch of 10.

---

### Pass 6 — ITIS (`itis_fallback.py`)

**API:** `https://www.itis.gov/ITISWebService/jsonservice`  
Two calls per taxon: `searchByScientificName` (retrieve TSN) then `getFullHierarchyFromTSN`.

**Fields added:** any of the seven standard ranks still `NaN` after Wikidata.

- Processes names one at a time; the first TSN returned by `searchByScientificName` is used.
- Full hierarchy is walked via `hierarchyList`; entries whose `rankName` (lowercased) matches a target field are stored.
- Particularly effective for vertebrates, including Squamata and Mammalia.
- Checkpoint: writes the CSV every 10 names; sleeps 0.5 s between queries.

---

## 4. Final Filtering (`filter_kingdoms.py`)

**Input:** `data/passes/TaxonBodyMass_ITIS_pass.csv`  
**Output:** `data/passes/TaxonBodyMass_curated.csv`

Removes rows whose `kingdom` field matches any of the following non-animal eukaryotic kingdoms:

| Removed |
|---|
| Plantae |
| Chromista |
| Fungi |
| Viridiplantae |

Rows with `kingdom` equal to `Animalia`, `Metazoa`, `Protozoa`, `Bacteria`, `Bacillati`, or `NaN` (unresolved) are retained. The script prints kingdom-level counts before and after filtering as a diagnostic.

The unfiltered `TaxonBodyMass_ITIS_pass.csv` is preserved as-is; `TaxonBodyMass_curated.csv` is the file consumed by downstream modelling steps.

---

## 5. Output Statistics

Source CSV: 39,155 rows, 39,155 unique taxa.

### Per-pass enrichment summary

| Pass | API | Taxa queried | Resolved | Missed | Cumulative % complete |
|---|---|---:|---:|---:|---:|
| 1 GBIF | GBIF species/match | 39,155 | 39,040 | 115 | 57.6% |
| 2 NCBI | NCBI Entrez | 16,590 | 13,799 | 2,791 | 92.6% |
| 3 WoRMS | WoRMS AphiaRecordsByMatchNames | 2,897 | 268 | 2,629 | 93.2% |
| 4 COL | COL ChecklistBank | 2,668 | 2,630 | 38 | 99.7% |
| 5 Wikidata | Wikidata SPARQL | 113 | 70 | 43 | 99.8% |
| 6 ITIS | ITIS JSON service | 89 | 36 | 53 | 99.8% |

**Taxa queried** — unique taxa with at least one missing taxonomy field going into that pass (all taxa for GBIF, which initialises the taxonomy columns).  
**Resolved** — taxa queried minus taxa in the missed-species log (i.e. received at least partial taxonomy from this pass).  
**Cumulative % complete** — percentage of all rows in the output CSV with all seven taxonomy fields (`kingdom`, `phylum`, `class`, `order`, `family`, `genus`, `species`) filled after this pass.

### filter_kingdoms step

| | Rows |
|---|---:|
| Input (ITIS pass) | 39,155 |
| Output (curated) | 38,373 |
| Removed | 782 |

Rows whose `kingdom` matched `Plantae`, `Chromista`, `Fungi`, or `Viridiplantae` were removed.

### Missed-species logs

Per-pass missed-species logs are written to:

- `data/passes/missed_species_gbif.txt`
- `data/passes/missed_species_ncbi.txt`
- `data/passes/missed_species_worms.txt`
- `data/passes/missed_species_col.txt`
- `data/passes/missed_species_wikidata.txt`
- `data/passes/missed_species_itis.txt`

These files and `TaxonBodyMass_curated.csv` are the authoritative record of pipeline yield for any given run. To regenerate the statistics table above, run `scripts/pipeline_stats.py` from the repo root.
