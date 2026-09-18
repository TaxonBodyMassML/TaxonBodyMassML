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

test_that(".resolve_interval_method returns valid methods unchanged", {
  expect_equal(TaxonBodyMassML:::.resolve_interval_method("stratified"), "stratified")
  expect_equal(TaxonBodyMassML:::.resolve_interval_method("pooled"),     "pooled")
})

test_that(".resolve_interval_method errors on invalid values", {
  expect_error(TaxonBodyMassML:::.resolve_interval_method("marginal"), "interval_method")
  expect_error(TaxonBodyMassML:::.resolve_interval_method(""),         "interval_method")
  expect_error(TaxonBodyMassML:::.resolve_interval_method(TRUE),       "interval_method")
})

test_that("predict_mass() errors on unknown method", {
  expect_error(
    TaxonBodyMassML::predict_mass("Homo sapiens", method = "NotAModel"),
    "Unknown method"
  )
})

test_that("predict_mass() errors on invalid interval_method", {
  expect_error(
    TaxonBodyMassML::predict_mass("Homo sapiens", interval_method = "marginal"),
    "interval_method"
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

  result <- TaxonBodyMassML::predict_mass("Canis lupus", confidence_interval = TRUE, lookup = FALSE)
  expect_true(all(c("lower_bound", "upper_bound", "confidence") %in% names(result)))
  expect_equal(result$confidence, 0.90)
  expect_lt(result$lower_bound, result$mass_g)
  expect_gt(result$upper_bound, result$mass_g)
})

test_that("predict_mass() returns custom CI level", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Mus musculus", confidence_interval = 0.50, lookup = FALSE)
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
  expect_equal(result$taxon, sp)
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

  r90 <- TaxonBodyMassML::predict_mass("Mus musculus", confidence_interval = 0.90, lookup = FALSE)
  r80 <- TaxonBodyMassML::predict_mass("Mus musculus", confidence_interval = 0.80, lookup = FALSE)
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
    "No species could be resolved"
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
  expect_equal(result$taxon, "Balanus glandula")
  expect_equal(result$matched_name, "Ballanus glandula")
  expect_true("matched_name" %in% names(result))
})

test_that("predict_mass() with fuzzy_match_name: matched_name is NA when no correction needed", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Balanus glandula",
                                          fuzzy_match_name = TRUE)
  expect_equal(result$taxon, "Balanus glandula")
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
  expect_true(is.na(result$taxon))
  expect_equal(result$matched_name, "Xyzzy_definitely_not_a_species_12345")
  expect_true(is.na(result$mass_g))
})

# ---------------------------------------------------------------------------
# Dictionary lookup and include_source
# ---------------------------------------------------------------------------

test_that("predict_mass() returns empirical mass for species in training data", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  # Nucella ostrina is in training data with mass_g = 0.7, source = "Novak_unpubl"
  result <- TaxonBodyMassML::predict_mass("Nucella ostrina")
  expect_equal(result$mass_g, 0.7)
})

test_that("predict_mass() with include_source returns source for dictionary hit", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Nucella ostrina", include_source = TRUE)
  expect_true("source" %in% names(result))
  expect_equal(result$source, "Novak_unpubl")
})

test_that("predict_mass() dict hit with CI has NA bounds", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Nucella ostrina",
                                          confidence_interval = TRUE)
  expect_true(all(c("lower_bound", "upper_bound", "confidence") %in% names(result)))
  expect_true(is.na(result$lower_bound))
  expect_true(is.na(result$upper_bound))
  expect_true(is.na(result$confidence))
})

test_that("predict_mass() with include_source returns tbmML_genus for model-inferred with known genus", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  # Nucella lima is not in training data but Nucella genus is known
  result <- TaxonBodyMassML::predict_mass("Nucella lima", include_source = TRUE)
  expect_true("source" %in% names(result))
  expect_equal(result$source, "tbmML_genus")
})

test_that("predict_mass() with include_source returns NA source for unresolvable taxon", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  suppressWarnings(
    result <- TaxonBodyMassML::predict_mass("Xyzzy_definitely_not_a_species_12345",
                                            include_source = TRUE)
  )
  expect_true("source" %in% names(result))
  expect_true(is.na(result$source))
})

test_that("predict_mass() preserves order with mixed dict/model/unresolved rows", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  sp <- c("Nucella ostrina",                    # dict hit
          "Canis lupus",                         # model-inferred
          "Xyzzy_definitely_not_a_species_12345") # unresolvable
  suppressWarnings(result <- TaxonBodyMassML::predict_mass(sp, include_source = TRUE))
  expect_equal(nrow(result), 3L)
  expect_equal(result$taxon[1L], "Nucella ostrina")
  expect_equal(result$mass_g[1L], 0.7)
  expect_equal(result$source[1L], "Novak_unpubl")
  expect_false(is.na(result$mass_g[2L]))
  expect_true(startsWith(result$source[2L], "tbmML_"))
  expect_true(is.na(result$mass_g[3L]))
  expect_true(is.na(result$source[3L]))
})

# ---------------------------------------------------------------------------
# lookup parameter
# ---------------------------------------------------------------------------

test_that("predict_mass() with lookup = FALSE routes dict species through model", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  # Nucella ostrina is in training data (mass_g = 0.7); with lookup = FALSE
  # it should be passed through the model and return a different value.
  result <- TaxonBodyMassML::predict_mass("Nucella ostrina", lookup = FALSE)
  expect_false(isTRUE(all.equal(result$mass_g, 0.7)))
})

test_that("predict_mass() with lookup = FALSE, include_source returns tbmML_ prefix", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass("Nucella ostrina",
                                          lookup = FALSE,
                                          include_source = TRUE)
  expect_true(startsWith(result$source, "tbmML_"))
})

# ---------------------------------------------------------------------------
# interval_method
# ---------------------------------------------------------------------------

test_that("predict_mass() stratified interval returns finite bounds for model-inferred taxon", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass(
    "Nucella lima",
    confidence_interval = TRUE,
    interval_method = "stratified"
  )
  expect_true(all(c("lower_bound", "upper_bound", "confidence") %in% names(result)))
  expect_true(is.finite(result$lower_bound))
  expect_true(is.finite(result$upper_bound))
  expect_lt(result$lower_bound, result$mass_g)
  expect_gt(result$upper_bound, result$mass_g)
})

test_that("predict_mass() pooled interval returns finite bounds for model-inferred taxon", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  result <- TaxonBodyMassML::predict_mass(
    "Nucella lima",
    confidence_interval = TRUE,
    interval_method = "pooled"
  )
  expect_true(is.finite(result$lower_bound))
  expect_true(is.finite(result$upper_bound))
  expect_lt(result$lower_bound, result$mass_g)
  expect_gt(result$upper_bound, result$mass_g)
})

test_that("predict_mass() stratified intervals equal pooled at genus level and differ at family level", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")

  # Species is not a model feature, so a genus-level query masks nothing and its
  # rank-specific residuals are the pooled residuals by design.
  genus_df <- data.frame(
    kingdom = "Animalia", phylum = "Mollusca", class = "Gastropoda",
    order = "Neogastropoda", family = "Muricidae", genus = "Nucella",
    species_resolved = "Nucella notaspecies", stringsAsFactors = FALSE
  )
  g_strat <- TaxonBodyMassML::predict_mass(genus_df, confidence_interval = TRUE,
                                           interval_method = "stratified")
  g_pool  <- TaxonBodyMassML::predict_mass(genus_df, confidence_interval = TRUE,
                                           interval_method = "pooled")
  expect_equal(g_strat$upper_bound - g_strat$lower_bound,
               g_pool$upper_bound  - g_pool$lower_bound)

  # A family-level query (unknown genus) uses the family-rank residuals.
  family_df <- genus_df
  family_df$genus <- "Zzznotagenus"
  f_strat <- TaxonBodyMassML::predict_mass(family_df, confidence_interval = TRUE,
                                           interval_method = "stratified")
  f_pool  <- TaxonBodyMassML::predict_mass(family_df, confidence_interval = TRUE,
                                           interval_method = "pooled")
  expect_false(isTRUE(all.equal(f_strat$upper_bound - f_strat$lower_bound,
                                f_pool$upper_bound  - f_pool$lower_bound)))
})

test_that("predict_mass() dict hit has NA bounds regardless of interval_method", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  testthat::skip_if_offline()

  r_strat <- TaxonBodyMassML::predict_mass(
    "Nucella ostrina", confidence_interval = TRUE, interval_method = "stratified"
  )
  expect_true(is.na(r_strat$lower_bound))
  expect_true(is.na(r_strat$upper_bound))
})

# ---------------------------------------------------------------------------
# Golden predictions: the XGBoost method must reproduce the training model
# exactly (guards against column-order, encoding and xgboost-version drift).
# ---------------------------------------------------------------------------

test_that("predict_mass() matches golden predictions for both methods", {
  testthat::skip_if(!TaxonBodyMassML:::.artifacts_cached(),
                    "Model artifacts not cached; skipping integration test.")
  golden <- file.path(testthat::test_path(), "..", "..", "..", "..",
                      "predictive_models", "results", "golden_predictions.json")
  testthat::skip_if_not(file.exists(golden), "golden_predictions.json not in this checkout")

  cases <- jsonlite::fromJSON(golden, simplifyDataFrame = TRUE)$cases
  df <- cases[, c("kingdom", "phylum", "class", "order", "family", "genus", "species")]
  names(df)[names(df) == "species"] <- "species_resolved"
  out <- TaxonBodyMassML::predict_mass(df, method = "XGBoost", lookup = FALSE)
  expect_lt(max(abs(log10(out$mass_g) - cases$log10_mass_g)), 1e-5)
  if (!is.null(cases$log10_mass_g_ee)) {
    out_ee <- TaxonBodyMassML::predict_mass(df, method = "EntityEmbeddings", lookup = FALSE)
    expect_lt(max(abs(log10(out_ee$mass_g) - cases$log10_mass_g_ee)), 1e-5)
  }
})
