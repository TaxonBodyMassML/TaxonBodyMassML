test_that(".parse_ncbi_xml extracts species and lineage ranks from fixture XML", {
  xml <- paste0(
    "<TaxaSet><Taxon>",
    "<ScientificName>Mus musculus</ScientificName>",
    "<LineageEx>",
    "<Taxon><Rank>kingdom</Rank><ScientificName>Metazoa</ScientificName></Taxon>",
    "<Taxon><Rank>phylum</Rank><ScientificName>Chordata</ScientificName></Taxon>",
    "<Taxon><Rank>class</Rank><ScientificName>Mammalia</ScientificName></Taxon>",
    "</LineageEx>",
    "</Taxon></TaxaSet>"
  )
  result <- TaxonBodyMassML:::.parse_ncbi_xml(xml)
  expect_equal(result[["species"]], "Mus musculus")
  expect_equal(result[["kingdom"]], "Metazoa")
  expect_equal(result[["phylum"]], "Chordata")
  expect_equal(result[["class"]], "Mammalia")
})

test_that(".parse_ncbi_xml returns empty list on malformed XML", {
  result <- TaxonBodyMassML:::.parse_ncbi_xml("not valid xml <<<")
  expect_equal(result, list())
})

test_that("tbm_options() returns all current options when called with no args", {
  opts <- TaxonBodyMassML::tbm_options()
  expect_type(opts, "list")
  expect_true("disk_cache" %in% names(opts))
  expect_true("progress" %in% names(opts))
})

test_that("tbm_options() sets a valid option", {
  old <- TaxonBodyMassML::tbm_options()$progress
  on.exit(TaxonBodyMassML::tbm_options(progress = old))
  TaxonBodyMassML::tbm_options(progress = FALSE)
  expect_false(TaxonBodyMassML::tbm_options()$progress)
})

test_that("tbm_options() errors on unknown option name", {
  expect_error(
    TaxonBodyMassML::tbm_options(not_an_option = TRUE),
    "Unknown option"
  )
})

test_that(".normalise_name lowercases, trims, and replaces underscores", {
  expect_equal(TaxonBodyMassML:::.normalise_name("Homo_sapiens"), "homo sapiens")
  expect_equal(TaxonBodyMassML:::.normalise_name("  Canis lupus  "), "canis lupus")
  expect_equal(TaxonBodyMassML:::.normalise_name("PANTHERA_LEO"), "panthera leo")
  expect_equal(TaxonBodyMassML:::.normalise_name("mus_musculus"), "mus musculus")
})

test_that(".normalise_name handles already-normalised names", {
  expect_equal(TaxonBodyMassML:::.normalise_name("homo sapiens"), "homo sapiens")
})

test_that("lookup_taxonomy returns a data.frame with the expected columns", {
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::lookup_taxonomy("Homo sapiens")
  expect_s3_class(result, "data.frame")
  expected_cols <- c("species", "kingdom", "phylum", "class", "order",
                     "family", "genus", "species_resolved")
  expect_true(all(expected_cols %in% names(result)))
})

test_that("lookup_taxonomy returns one row per input name", {
  testthat::skip_if_offline()

  sp <- c("Homo sapiens", "Mus musculus", "Canis lupus")
  result <- TaxonBodyMassML::lookup_taxonomy(sp)
  expect_equal(nrow(result), length(sp))
  expect_equal(result$species, sp)
})

test_that("lookup_taxonomy fills known ranks for Homo sapiens", {
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::lookup_taxonomy("Homo sapiens")
  expect_false(is.na(result$kingdom))
  expect_false(is.na(result$phylum))
  expect_false(is.na(result$species_resolved))
})

test_that("lookup_taxonomy warns and returns NA rows for unresolvable names", {
  testthat::skip_if_offline()

  expect_warning(
    result <- TaxonBodyMassML::lookup_taxonomy("Xyzzy_definitely_not_a_species_12345"),
    "Could not resolve taxonomy"
  )
  expect_equal(nrow(result), 1L)
  expect_true(is.na(result$species_resolved))
})

test_that("lookup_taxonomy session cache avoids duplicate lookups", {
  testthat::skip_if_offline()

  result1 <- TaxonBodyMassML::lookup_taxonomy("Felis catus")
  result2 <- TaxonBodyMassML::lookup_taxonomy("Felis catus")
  expect_equal(result1, result2)
})

test_that("lookup_taxonomy handles underscore-separated names", {
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::lookup_taxonomy("Homo_sapiens")
  expect_false(is.na(result$species_resolved))
})
