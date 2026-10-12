skip_msg <- "GBIF integration tests disabled; set TAXONBODYMASSML_RUN_INTEGRATION=1 to enable."

test_that(".gbif_fuzzy_name corrects a misspelled genus via HIGHERRANK fallback", {
  skip_if(Sys.getenv("TAXONBODYMASSML_RUN_INTEGRATION") != "1", skip_msg)
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Ballanus glandula")
  expect_equal(result, "Balanus glandula")
})

test_that(".gbif_fuzzy_name corrects a misspelled epithet via direct FUZZY match", {
  skip_if(Sys.getenv("TAXONBODYMASSML_RUN_INTEGRATION") != "1", skip_msg)
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Balanus glandulla")
  expect_equal(result, "Balanus glandula")
})

test_that(".gbif_fuzzy_name corrects both a misspelled genus and epithet", {
  skip_if(Sys.getenv("TAXONBODYMASSML_RUN_INTEGRATION") != "1", skip_msg)
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Ballanus glanddula")
  expect_equal(result, "Balanus glandula")
})

test_that(".gbif_fuzzy_name returns NA for a completely unrecognisable name", {
  skip_if(Sys.getenv("TAXONBODYMASSML_RUN_INTEGRATION") != "1", skip_msg)
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Xyzzy notaspecies12345")
  expect_true(is.na(result))
})

test_that("correct_species_names returns a data.frame with the right columns and values", {
  skip_if(Sys.getenv("TAXONBODYMASSML_RUN_INTEGRATION") != "1", skip_msg)
  testthat::skip_if_offline()
  result <- TaxonBodyMassML::correct_species_names(
    c("Ballanus glandula", "Balanus glandulla", "Ballanus glanddula")
  )
  expect_s3_class(result, "data.frame")
  expect_named(result, c("input_name", "matched_name"))
  expect_equal(result$matched_name, rep("Balanus glandula", 3L))
})

test_that(".gbif_fuzzy_name returns the failed-request sentinel on network error", {
  ns <- asNamespace("TaxonBodyMassML")
  sentinel <- get(".FUZZY_REQUEST_FAILED", envir = ns)
  old <- get(".tbm_get", envir = ns)
  unlockBinding(".tbm_get", ns)
  on.exit({
    unlockBinding(".tbm_get", ns)
    assign(".tbm_get", old, envir = ns)
    lockBinding(".tbm_get", ns)
  }, add = TRUE)
  assign(".tbm_get", function(...) stop("network error"), envir = ns)

  result <- get(".gbif_fuzzy_name", envir = ns)("Nucela lima")
  expect_equal(result, sentinel)
})

test_that("correct_species_names warns on request failure and returns NA for the failed name", {
  ns <- asNamespace("TaxonBodyMassML")
  old <- get(".tbm_get", envir = ns)
  unlockBinding(".tbm_get", ns)
  on.exit({
    unlockBinding(".tbm_get", ns)
    assign(".tbm_get", old, envir = ns)
    lockBinding(".tbm_get", ns)
  }, add = TRUE)
  assign(".tbm_get", function(...) stop("network error"), envir = ns)

  expect_warning(
    result <- TaxonBodyMassML::correct_species_names("Nucela lima"),
    "Fuzzy lookup failed for 1 name"
  )
  expect_true(is.na(result$matched_name[1L]))
  expect_equal(result$input_name[1L], "Nucela lima")
})

test_that("correct_species_names warns only for failed names, not no-match names", {
  ns <- asNamespace("TaxonBodyMassML")
  sentinel <- get(".FUZZY_REQUEST_FAILED", envir = ns)
  old_fn <- get(".gbif_fuzzy_name", envir = ns)
  unlockBinding(".gbif_fuzzy_name", ns)
  on.exit({
    unlockBinding(".gbif_fuzzy_name", ns)
    assign(".gbif_fuzzy_name", old_fn, envir = ns)
    lockBinding(".gbif_fuzzy_name", ns)
  }, add = TRUE)

  # "Nucela lima" fails the request; "Xyzzy notaspecies" genuinely has no match
  assign(".gbif_fuzzy_name", function(name) {
    if (identical(name, "Nucela lima")) sentinel else NA_character_
  }, envir = ns)

  expect_warning(
    result <- TaxonBodyMassML::correct_species_names(c("Nucela lima", "Xyzzy notaspecies")),
    "Fuzzy lookup failed for 1 name"
  )
  expect_true(is.na(result$matched_name[1L]))  # failed request -> NA
  expect_true(is.na(result$matched_name[2L]))  # no match -> NA (no extra warning)
})
