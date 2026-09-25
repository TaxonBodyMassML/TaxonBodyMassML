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

test_that("every mapped Bibcite is present in the bundled bibliography", {
  map <- TaxonBodyMassML:::.read_citeids()
  bib <- paste(readLines(TaxonBodyMassML::get_citations(), encoding = "UTF-8",
                         warn = FALSE), collapse = "\n")
  missing <- unique(map)[vapply(unique(map), function(k) {
    is.null(TaxonBodyMassML:::.extract_bib_entry(bib, k))
  }, logical(1))]
  expect_length(missing, 0)
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
