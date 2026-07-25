test_that(".gbif_fuzzy_name corrects a misspelled genus via HIGHERRANK fallback", {
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Ballanus glandula")
  expect_equal(result, "Balanus glandula")
})

test_that(".gbif_fuzzy_name corrects a misspelled epithet via direct FUZZY match", {
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Balanus glandulla")
  expect_equal(result, "Balanus glandula")
})

test_that(".gbif_fuzzy_name corrects both a misspelled genus and epithet", {
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Ballanus glanddula")
  expect_equal(result, "Balanus glandula")
})

test_that(".gbif_fuzzy_name returns NA for a completely unrecognisable name", {
  testthat::skip_if_offline()
  result <- TaxonBodyMassML:::.gbif_fuzzy_name("Xyzzy notaspecies12345")
  expect_true(is.na(result))
})

test_that("correct_species_names returns a data.frame with the right columns and values", {
  testthat::skip_if_offline()
  result <- TaxonBodyMassML::correct_species_names(
    c("Ballanus glandula", "Balanus glandulla", "Ballanus glanddula")
  )
  expect_s3_class(result, "data.frame")
  expect_named(result, c("input_name", "matched_name"))
  expect_equal(result$matched_name, rep("Balanus glandula", 3L))
})
