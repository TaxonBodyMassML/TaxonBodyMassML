# Tests for get_citations() and create_bib(). None require network access or
# the model artifacts: they use the bundled CSV/bib and small inline fixtures.

mini_bib <- paste(
  "%% This BibTeX bibliography file was created using BibDesk.",
  "",
  "@article{Smith-Jones:2020aa,",
  "\tauthor = {Smith, A and Jones, B{\\'e}n},",
  "\ttitle = {A {Nested} {{Title}}},",
  "\tyear = {2020}}",
  "",
  "@book{Smith-Jones:2020ab,",
  "\ttitle = {Other},",
  "\tyear = {2021}}",
  "",
  sep = "\n"
)

test_that("get_citations() and .citeid_path() point to bundled files", {
  bib <- TaxonBodyMassML::get_citations()
  csv <- TaxonBodyMassML:::.citeid_path()
  expect_true(file.exists(bib))
  expect_true(file.exists(csv))
  expect_match(bib, "\\.bib$")
  expect_match(csv, "\\.csv$")
})

test_that(".normalise_label() unifies dashes, diacritics and whitespace", {
  n <- TaxonBodyMassML:::.normalise_label
  expect_equal(n("Martinez\u2010Palacios_1992"), "Martinez-Palacios_1992")
  expect_equal(n("Cervig\u00f3n_1992"), "Cervigon_1992")
  expect_equal(n("Galv\u00e1n-Villa_2021"), "Galvan-Villa_2021")
  expect_equal(n(" fishbase\u00a0"), "fishbase")
  expect_equal(n("Meiri_2018"), "Meiri_2018")
  expect_true(is.na(n(NA_character_)))
})

test_that(".split_sources() splits on ';', trims, drops NA/empty/tbmML_", {
  v <- c("Novak_unpubl", "Feldman_etal_2016; Meiri_2018", "tbmML_genus",
         "tbmML_UNK", NA, "", " Meiri_2018 ")
  expect_equal(TaxonBodyMassML:::.split_sources(v),
               c("Novak_unpubl", "Feldman_etal_2016", "Meiri_2018"))
  expect_equal(TaxonBodyMassML:::.split_sources(c(NA, "tbmML_family")),
               character(0))
})

test_that(".extract_bib_entry() returns the entry verbatim and anchors on the exact key", {
  ext <- TaxonBodyMassML:::.extract_bib_entry
  e <- ext(mini_bib, "Smith-Jones:2020aa")
  expect_match(e, "^@article\\{Smith-Jones:2020aa,")
  expect_match(e, "\\{\\{Title\\}\\}\\},\n\tyear = \\{2020\\}\\}$")
  expect_false(grepl("Other", e, fixed = TRUE))
  # last entry in file (no following '@') is returned to EOF, trailing blanks trimmed
  e2 <- ext(mini_bib, "Smith-Jones:2020ab")
  expect_match(e2, "^@book\\{Smith-Jones:2020ab,")
  expect_match(e2, "\\{2021\\}\\}$")
  # key prefix must not match a longer key
  expect_null(ext(mini_bib, "Smith-Jones:2020a"))
  expect_null(ext(mini_bib, "Nobody:9999aa"))
})

test_that(".read_citeids() maps CiteID to Bibcite and drops NA rows", {
  map <- TaxonBodyMassML:::.read_citeids()
  expect_type(map, "character")
  expect_equal(unname(map[["Meiri_2018"]]), "Meiri:2018aa")
  expect_false(any(is.na(names(map))))
  expect_false(any(names(map) == ""))
})

test_that("every mapped Bibcite of the compilation bibliography is present in it", {
  # Keys with bib_file == "PrimaryCitations" live in the primary bibliography
  # (checked below); the readers themselves use only the first two columns.
  map  <- TaxonBodyMassML:::.read_citeids()
  cite <- utils::read.csv(TaxonBodyMassML:::.citeid_path(), stringsAsFactors = FALSE,
                          encoding = "UTF-8", na.strings = character(0))
  primary_keys <- cite$Bibcite[cite$bib_file == "PrimaryCitations"]
  bib <- paste(readLines(TaxonBodyMassML::get_citations(), encoding = "UTF-8",
                         warn = FALSE), collapse = "\n")
  keys <- setdiff(unique(map), primary_keys)
  missing <- keys[vapply(keys, function(k) {
    is.null(TaxonBodyMassML:::.extract_bib_entry(bib, k))
  }, logical(1))]
  expect_length(missing, 0)
  expect_gt(length(primary_keys), 0L)
  expect_true(all(vapply(primary_keys, function(k) {       # not duplicated across bibs
    is.null(TaxonBodyMassML:::.extract_bib_entry(bib, k))
  }, logical(1))))
})

test_that("create_bib() writes mapped entries, skips tbmML_, warns on unmapped", {
  x <- data.frame(
    taxon  = c("a", "b", "c", "d"),
    mass_g = c(1, 2, 3, NA),
    source = c("Nobody_9999", "Feldman_etal_2016; Meiri_2018", "tbmML_genus", NA),
    stringsAsFactors = FALSE
  )
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  expect_warning(out <- TaxonBodyMassML::create_bib(x, file = f), "Nobody_9999")
  expect_equal(normalizePath(out), normalizePath(f))
  txt <- readLines(f, encoding = "UTF-8")
  expect_match(txt[1], "^%% TaxonBodyMassML create_bib\\(\\): 2 data-source citation\\(s\\) for 4 taxa$")
  expect_true(any(grepl("^@article\\{Feldman:2016aa,", txt)))
  expect_true(any(grepl("^@article\\{Meiri:2018aa,", txt)))
  expect_false(any(grepl("tbmML", txt, fixed = TRUE)))
  expect_false(any(grepl("Nobody", txt, fixed = TRUE)))
})

test_that("create_bib() matches labels that differ only in dash or accent", {
  x <- data.frame(source = c("Martinez\u2010Palacios_1992", "Cervig\u00f3n_1992"),
                  stringsAsFactors = FALSE)
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  expect_no_warning(TaxonBodyMassML::create_bib(x, file = f))
  txt <- readLines(f, encoding = "UTF-8")
  expect_true(any(grepl("^@[a-z]+\\{Martinez-Palacios:1992aa,", txt)))
  expect_true(any(grepl("^@[a-z]+\\{Cervigon:1992aa,", txt)))
})

test_that("create_bib() with only model-inferred rows writes an empty bibliography", {
  x <- data.frame(source = c("tbmML_genus", "tbmML_UNK", NA), stringsAsFactors = FALSE)
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  expect_no_warning(TaxonBodyMassML::create_bib(x, file = f))
  txt <- readLines(f, encoding = "UTF-8")
  expect_match(txt[1], "0 data-source citation\\(s\\) for 3 taxa")
  expect_false(any(grepl("^@", txt)))
})

test_that("create_bib() errors on bad input", {
  expect_error(TaxonBodyMassML::create_bib(data.frame(taxon = "x")), "source")
  expect_error(TaxonBodyMassML::create_bib(list(source = "a")), "data.frame")
  expect_error(TaxonBodyMassML::create_bib(data.frame(source = "a"), file = ""), "file")
})

# ---------------------------------------------------------------------------
# Citation levels (TaxonBodyMass_DB issue #1 / TaxonBodyMassML #21). The
# provenance table and the primary bibliography are model artifacts; the tests
# point the package at offline fixtures copied from TaxonBodyMass_DB (every
# accepted row of the provenance table plus a few conversion, self, pending,
# uningested and unreferenced rows).
# ---------------------------------------------------------------------------

accepted_status <- c("certain", "approved", "nodoi_approved")

local_offline_provenance <- function(env = parent.frame()) {
  testthat::local_mocked_bindings(
    .primary_bib_path      = function() testthat::test_path("fixtures", "PrimaryCitations_BodyMass.bib"),
    .provenance_table_path = function() testthat::test_path("fixtures", "provenance_subset.csv.gz"),
    .package = "TaxonBodyMassML",
    .env = env
  )
}

bib_keys <- function(path) {
  txt <- readLines(path, encoding = "UTF-8", warn = FALSE)
  sub("^@[A-Za-z]+\\{([^,]+),.*$", "\\1", grep("^@[A-Za-z]+\\{", txt, value = TRUE))
}

test_that("get_citations() returns the bundled bib, the primary bib, or both", {
  local_offline_provenance()
  src <- TaxonBodyMassML::get_citations()
  expect_identical(src, TaxonBodyMassML::get_citations("source"))
  expect_match(basename(src), "^Citations_BodyMass\\.bib$")
  prim <- TaxonBodyMassML::get_citations("primary")
  expect_match(basename(prim), "^PrimaryCitations_BodyMass\\.bib$")
  expect_match(readLines(prim, n = 1L), "^%% GENERATED")
  both <- TaxonBodyMassML::get_citations("all")
  expect_identical(unname(both), c(src, prim))
  expect_identical(names(both), c("source", "primary"))
})

test_that("an invalid level is rejected", {
  local_offline_provenance()
  expect_error(TaxonBodyMassML::get_citations("secondary"), "level")
  expect_error(TaxonBodyMassML::create_bib(data.frame(source = "Meiri_2018"), level = "Primary"),
               "level")
  expect_error(TaxonBodyMassML::create_bib(data.frame(source = "Meiri_2018"), level = NA), "level")
  expect_error(TaxonBodyMassML::create_bib(data.frame(source = "Meiri_2018"),
                                           level = c("source", "primary")), "level")
})

test_that(".read_provenance() reads the gz with the documented columns and types", {
  local_offline_provenance()
  prov <- TaxonBodyMassML:::.read_provenance()
  expect_identical(names(prov), TaxonBodyMassML:::.PROVENANCE_COLS)
  expect_type(prov$hop, "integer")
  expect_type(prov$n_records, "integer")
  expect_true(anyNA(prov$match_status))             # literal "NA" read as missing
  expect_false(any(prov$primary_bibcite == "NA", na.rm = TRUE))
  expect_true(all(prov$n_records >= 1L))
})

test_that("the primary CiteIDs of the CiteID map are in the primary bibliography", {
  local_offline_provenance()
  cite <- utils::read.csv(TaxonBodyMassML:::.citeid_path(), stringsAsFactors = FALSE,
                          encoding = "UTF-8", na.strings = character(0))
  expect_identical(names(cite)[1:2], c("Bibcite", "CiteID"))  # the readers use these only
  expect_setequal(unique(cite$role), c("source", "conversion", "primary"))
  prim <- paste(readLines(TaxonBodyMassML::get_citations("primary"), encoding = "UTF-8",
                          warn = FALSE), collapse = "\n")
  keys <- cite$Bibcite[cite$bib_file == "PrimaryCitations"]
  expect_gt(length(keys), 0L)
  missing <- keys[vapply(keys, function(k) {
    is.null(TaxonBodyMassML:::.extract_bib_entry(prim, k))
  }, logical(1))]
  expect_length(missing, 0L)
})

test_that("every accepted primary_bibcite has an entry in one of the two bibs", {
  local_offline_provenance()
  prov <- TaxonBodyMassML:::.read_provenance()
  acc  <- prov[prov$match_status %in% accepted_status |
                 (!is.na(prov$provenance_type) & prov$provenance_type == "conversion_factor"), ]
  keys <- sort(unique(stats::na.omit(acc$primary_bibcite)))
  expect_gt(length(keys), 0L)
  src  <- paste(readLines(TaxonBodyMassML::get_citations("source"), encoding = "UTF-8",
                          warn = FALSE), collapse = "\n")
  prim <- paste(readLines(TaxonBodyMassML::get_citations("primary"), encoding = "UTF-8",
                          warn = FALSE), collapse = "\n")
  missing <- keys[vapply(keys, function(k) {
    is.null(TaxonBodyMassML:::.extract_bib_entry(prim, k)) &&
      is.null(TaxonBodyMassML:::.extract_bib_entry(src, k))
  }, logical(1))]
  expect_length(missing, 0L)
})

test_that("create_bib(level = 'primary') on the first accepted provenance row writes its key", {
  local_offline_provenance()
  prov <- TaxonBodyMassML:::.read_provenance()
  row  <- prov[prov$match_status %in% accepted_status, ][1L, ]
  x <- data.frame(taxon = row$species, mass_g = 1, source = row$source_mass,
                  source_taxon = row$species, stringsAsFactors = FALSE)
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  TaxonBodyMassML::create_bib(x, file = f, level = "primary")
  txt <- readLines(f, encoding = "UTF-8")
  expect_match(txt[1], "primary-reference citation\\(s\\) for 1 taxa$")
  expect_true(row$primary_bibcite %in% bib_keys(f))
  expect_false(row$source_bibcite %in% bib_keys(f))  # the compilation is not cited here
})

test_that("create_bib(level = 'primary') on the first provenance row (unresolved) warns, writes nothing", {
  local_offline_provenance()
  row <- TaxonBodyMassML:::.read_provenance()[1L, ]
  expect_true(row$hop >= 1L && !row$match_status %in% accepted_status)
  x <- data.frame(source = row$source_mass, source_taxon = row$species, stringsAsFactors = FALSE)
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  expect_warning(TaxonBodyMassML::create_bib(x, file = f, level = "primary"), "not yet resolved")
  txt <- readLines(f, encoding = "UTF-8")
  expect_match(txt[1], "^%% TaxonBodyMassML create_bib\\(\\): 0 primary-reference citation\\(s\\) for 1 taxa$")
  expect_length(bib_keys(f), 0L)
})

test_that("create_bib(level = 'primary') includes conversion-factor references", {
  local_offline_provenance()
  prov <- TaxonBodyMassML:::.read_provenance()
  conv <- prov[!is.na(prov$provenance_type) & prov$provenance_type == "conversion_factor", ]
  sp   <- conv$species[1L]
  expected <- unique(conv$primary_bibcite[conv$species == sp])
  x <- data.frame(source = conv$source_mass[1L], source_taxon = sp, stringsAsFactors = FALSE)
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  suppressWarnings(TaxonBodyMassML::create_bib(x, file = f, level = "primary"))
  expect_true(all(expected %in% bib_keys(f)))
})

test_that("create_bib(level = 'all') is the union of both levels without duplicate keys", {
  local_offline_provenance()
  prov <- TaxonBodyMassML:::.read_provenance()
  acc  <- prov[prov$match_status %in% accepted_status, ]
  conv <- prov[!is.na(prov$provenance_type) & prov$provenance_type == "conversion_factor", ]
  # Kiorboe_2013 is a data source (source level) and a conversion-factor
  # reference of other sources (primary level): the key must appear once.
  k_src  <- acc[acc$source_mass == "Kiorboe_2013", ][1L, ]
  k_conv <- conv[!is.na(conv$primary_cite_id) & conv$primary_cite_id == "Kiorboe_2013", ][1L, ]
  x <- data.frame(
    taxon        = c(k_src$species, k_conv$species, "Nucella lima"),
    source       = c(k_src$source_mass, k_conv$source_mass, "tbmML_genus"),
    source_taxon = c(k_src$species, k_conv$species, NA),
    stringsAsFactors = FALSE
  )
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  suppressWarnings(TaxonBodyMassML::create_bib(x, file = f, level = "all"))
  keys <- bib_keys(f)
  expect_false(any(duplicated(keys)))
  expect_equal(sum(keys == "Kiorboe:2013aa"), 1L)
  expect_true(k_src$primary_bibcite %in% keys)   # primary reference of the Kiorboe species
  expect_true(k_conv$source_bibcite %in% keys)   # the data source of the other species
  hdr <- readLines(f, n = 1L, encoding = "UTF-8")
  expect_match(hdr, "data-source and [0-9]+ primary-reference citation\\(s\\)")
  expect_match(hdr, sprintf("\\(%d unique\\) for 3 taxa$", length(keys)))
})

test_that("create_bib(level = 'primary') joins on source_taxon, species_resolved, then taxon", {
  local_offline_provenance()
  prov <- TaxonBodyMassML:::.read_provenance()
  row  <- prov[prov$match_status %in% accepted_status, ][1L, ]
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  x <- data.frame(source = row$source_mass, species_resolved = row$species,
                  stringsAsFactors = FALSE)
  w <- testthat::capture_warnings(TaxonBodyMassML::create_bib(x, file = f, level = "primary"))
  expect_false(any(grepl("joining the provenance table on `taxon`", w, fixed = TRUE)))
  expect_true(row$primary_bibcite %in% bib_keys(f))
  x <- data.frame(taxon = row$species, source = row$source_mass, stringsAsFactors = FALSE)
  expect_warning(
    suppressWarnings(TaxonBodyMassML::create_bib(x, file = f, level = "primary"),
                     classes = character(0)),
    "joining the provenance table on `taxon`"
  )
  expect_true(row$primary_bibcite %in% bib_keys(f))
})

test_that("create_bib(level = 'primary') warns on species absent from the provenance table", {
  local_offline_provenance()
  x <- data.frame(source = "Meiri_2018", source_taxon = "Zzzz notaspecies",
                  stringsAsFactors = FALSE)
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  expect_warning(TaxonBodyMassML::create_bib(x, file = f, level = "primary"),
                 "absent from the provenance table")
  expect_length(bib_keys(f), 0L)
})

test_that("create_bib(level = 'all') with only model rows writes an empty bibliography", {
  local_offline_provenance()
  x <- data.frame(source = c("tbmML_genus", NA), source_taxon = c(NA, NA),
                  stringsAsFactors = FALSE)
  f <- tempfile(fileext = ".bib")
  on.exit(unlink(f))
  expect_no_warning(TaxonBodyMassML::create_bib(x, file = f, level = "all"))
  txt <- readLines(f, encoding = "UTF-8")
  expect_match(txt[1], "0 data-source and 0 primary-reference citation\\(s\\) \\(0 unique\\) for 2 taxa")
  expect_false(any(grepl("^@", txt)))
})

test_that("level = 'source' output is unchanged by the level argument", {
  local_offline_provenance()
  x <- data.frame(source = "Meiri_2018", source_taxon = "Anolis carolinensis",
                  stringsAsFactors = FALSE)
  f1 <- tempfile(fileext = ".bib"); f2 <- tempfile(fileext = ".bib")
  on.exit(unlink(c(f1, f2)))
  TaxonBodyMassML::create_bib(x, file = f1)
  TaxonBodyMassML::create_bib(x, file = f2, level = "source")
  expect_identical(readLines(f1), readLines(f2))
  expect_identical(readLines(f1, n = 1L),
                   "%% TaxonBodyMassML create_bib(): 1 data-source citation(s) for 1 taxa")
})
