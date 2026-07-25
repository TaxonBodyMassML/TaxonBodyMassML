test_that(".resolve_ci_level returns NULL for FALSE", {
  expect_null(TaxonBodyMassML:::.resolve_ci_level(FALSE))
})

test_that(".resolve_ci_level returns 0.90 for TRUE", {
  expect_equal(TaxonBodyMassML:::.resolve_ci_level(TRUE), 0.90)
})

test_that(".resolve_ci_level returns the numeric value for a float in (0, 1)", {
  expect_equal(TaxonBodyMassML:::.resolve_ci_level(0.80), 0.80)
  expect_equal(TaxonBodyMassML:::.resolve_ci_level(0.50), 0.50)
})

test_that(".resolve_ci_level errors on invalid values", {
  expect_error(TaxonBodyMassML:::.resolve_ci_level(0),   "confidence_interval")
  expect_error(TaxonBodyMassML:::.resolve_ci_level(1),   "confidence_interval")
  expect_error(TaxonBodyMassML:::.resolve_ci_level(1.5), "confidence_interval")
  expect_error(TaxonBodyMassML:::.resolve_ci_level(-0.1),"confidence_interval")
  expect_error(TaxonBodyMassML:::.resolve_ci_level("bad"),"confidence_interval")
})

test_that("predict_mass() errors on unknown method", {
  expect_error(
    TaxonBodyMassML::predict_mass("Homo sapiens", method = "NotAModel"),
    "Unknown method"
  )
})

test_that("predict_mass() errors when data.frame is missing required columns", {
  bad_df <- data.frame(kingdom = "Animalia", stringsAsFactors = FALSE)
  expect_error(
    TaxonBodyMassML::predict_mass(bad_df),
    "missing columns"
  )
})

test_that("predict_mass() errors when data.frame has some but not all required columns", {
  partial_df <- data.frame(
    kingdom  = "Animalia",
    phylum   = "Chordata",
    class    = "Mammalia",
    stringsAsFactors = FALSE
  )
  expect_error(
    TaxonBodyMassML::predict_mass(partial_df),
    "missing columns"
  )
})

# ---------------------------------------------------------------------------
# Integration tests — require downloaded artifacts
# ---------------------------------------------------------------------------

test_that("predict_mass() returns mass_g for a single species", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Homo sapiens")
  expect_s3_class(result, "data.frame")
  expect_true("mass_g" %in% names(result))
  expect_equal(nrow(result), 1L)
  expect_true(is.numeric(result$mass_g))
  expect_gt(result$mass_g, 0)
})

test_that("predict_mass() returns CI columns when confidence_interval = TRUE", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Canis lupus", confidence_interval = TRUE)
  expect_true(all(c("lower_bound", "upper_bound", "confidence") %in% names(result)))
  expect_equal(result$confidence, 0.90)
  expect_lt(result$lower_bound, result$mass_g)
  expect_gt(result$upper_bound, result$mass_g)
})

test_that("predict_mass() returns custom CI level", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Mus musculus", confidence_interval = 0.50)
  expect_equal(result$confidence, 0.50)
})

test_that("predict_mass() with include_taxonomy = TRUE includes taxonomy columns", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Panthera leo", include_taxonomy = TRUE)
  tax_cols <- c("kingdom", "phylum", "class", "order", "family", "genus",
                "species_resolved")
  expect_true(all(tax_cols %in% names(result)))
})

test_that("predict_mass() preserves input order for multiple species", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  sp <- c("Homo sapiens", "Mus musculus", "Panthera leo")
  result <- TaxonBodyMassML::predict_mass(sp)
  expect_equal(result$species, sp)
})

test_that("predict_mass() accepts pre-resolved data.frame input", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  tax <- TaxonBodyMassML::lookup_taxonomy("Canis lupus")
  result <- TaxonBodyMassML::predict_mass(tax)
  expect_s3_class(result, "data.frame")
  expect_true("mass_g" %in% names(result))
})

test_that("predict_mass() returns wider interval at higher coverage level", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  r90 <- TaxonBodyMassML::predict_mass("Mus musculus", confidence_interval = 0.90)
  r80 <- TaxonBodyMassML::predict_mass("Mus musculus", confidence_interval = 0.80)
  width90 <- r90$upper_bound - r90$lower_bound
  width80 <- r80$upper_bound - r80$lower_bound
  expect_gt(width90, width80)
})

test_that("predict_mass() returns NA mass_g and warns for unresolvable species", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  expect_warning(
    result <- TaxonBodyMassML::predict_mass("Xyzzy_definitely_not_a_species_12345"),
    "Could not resolve"
  )
  expect_equal(nrow(result), 1L)
  expect_true(is.na(result$mass_g))
})

# ---------------------------------------------------------------------------
# fuzzy_match_name column semantics
# ---------------------------------------------------------------------------

test_that("predict_mass() with fuzzy_match_name: corrected name in species, original in matched_name", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Ballanus glandula",
                                          fuzzy_match_name = TRUE)
  expect_equal(result$species, "Balanus glandula")
  expect_equal(result$matched_name, "Ballanus glandula")
  expect_true("matched_name" %in% names(result))
})

test_that("predict_mass() with fuzzy_match_name: matched_name is NA when no correction needed", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Balanus glandula",
                                          fuzzy_match_name = TRUE)
  expect_equal(result$species, "Balanus glandula")
  expect_true(is.na(result$matched_name))
  expect_true("matched_name" %in% names(result))
})

test_that("predict_mass() with fuzzy_match_name: species NA and matched_name set when GBIF finds no match", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  suppressWarnings(
    result <- TaxonBodyMassML::predict_mass("Xyzzy_definitely_not_a_species_12345",
                                            fuzzy_match_name = TRUE)
  )
  expect_true(is.na(result$species))
  expect_equal(result$matched_name, "Xyzzy_definitely_not_a_species_12345")
  expect_true(is.na(result$mass_g))
})
