test_that("tbm_clear_cache(session = TRUE) clears in-memory cache", {
  TaxonBodyMassML::tbm_clear_cache(disk = FALSE, session = TRUE)
  expect_equal(length(ls(envir = TaxonBodyMassML:::.tbm_cache)), 0L)
})

test_that("tbm_clear_cache() resets artifacts_ok flag", {
  TaxonBodyMassML::tbm_clear_cache(disk = FALSE, session = TRUE)
  expect_false(isTRUE(TaxonBodyMassML:::.model_env$artifacts_ok))
})

test_that("tbm_clear_cache(disk = TRUE) removes taxonomy directory", {
  cache_dir <- tools::R_user_dir("TaxonBodyMassML", "cache")
  tax_dir   <- file.path(cache_dir, "taxonomy")
  dir.create(tax_dir, recursive = TRUE, showWarnings = FALSE)
  expect_true(dir.exists(tax_dir))

  TaxonBodyMassML::tbm_clear_cache(disk = TRUE, session = FALSE)
  expect_false(dir.exists(tax_dir))
})

test_that("predict_mass() returns zero-row data.frame for character(0)", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  result <- TaxonBodyMassML::predict_mass(character(0))
  expect_s3_class(result, "data.frame")
  expect_equal(nrow(result), 0L)
  expect_true("taxon" %in% names(result))
  expect_true("mass_g" %in% names(result))
})

test_that("lookup_taxonomy() returns zero-row data.frame for character(0)", {
  testthat::skip_if_offline()
  result <- TaxonBodyMassML::lookup_taxonomy(character(0))
  expect_s3_class(result, "data.frame")
  expect_equal(nrow(result), 0L)
})

test_that("lookup_taxonomy() with disk_cache = TRUE writes and reads from cache", {
  testthat::skip_if_offline()

  TaxonBodyMassML::tbm_options(disk_cache = TRUE)
  on.exit({
    TaxonBodyMassML::tbm_options(disk_cache = FALSE)
    TaxonBodyMassML::tbm_clear_cache(disk = TRUE, session = TRUE)
  })

  result1 <- TaxonBodyMassML::lookup_taxonomy("Homo sapiens")
  result2 <- TaxonBodyMassML::lookup_taxonomy("Homo sapiens")

  expect_equal(result1, result2)
  expect_false(is.na(result1$kingdom))

  cache_dir <- tools::R_user_dir("TaxonBodyMassML", "cache")
  tax_dir   <- file.path(cache_dir, "taxonomy")
  expect_true(dir.exists(tax_dir))
})
