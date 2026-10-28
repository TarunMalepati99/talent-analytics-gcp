# Independent R replication of analysis/attrition_significance.py.
#
# Re-codes the factors from the raw employee extract and re-runs the chi-square
# tests (with Benjamini-Hochberg correction), the multivariable logistic
# regression and the overtime x early-tenure likelihood-ratio test in base R.
# scripts/cross_check_stats.py then compares these outputs with Python's and
# fails the build if they disagree, so no number reaches a report unchecked.
#
# Base R only (stats + utils), so it runs anywhere R is installed:
#   Rscript analysis/r/attrition_significance.R warehouse/analysis_base.csv analysis/model_spec.csv reports/stats

args <- commandArgs(trailingOnly = TRUE)
input_path <- if (length(args) >= 1) args[1] else "warehouse/analysis_base.csv"
spec_path  <- if (length(args) >= 2) args[2] else "analysis/model_spec.csv"
out_dir    <- if (length(args) >= 3) args[3] else "reports/stats"

ALPHA <- 0.05
EARLY_TENURE_YEARS <- 2

spec <- read.csv(spec_path, colClasses = "character", check.names = FALSE)
df   <- read.csv(input_path, colClasses = "character", check.names = FALSE)

df$is_attrited      <- as.integer(df$is_attrited)
df$years_at_company <- as.numeric(df$years_at_company)
for (i in seq_len(nrow(spec))) {
  f <- spec$factor[i]
  if (spec$kind[i] %in% c("binary", "ordinal")) df[[f]] <- as.numeric(df[[f]])
}

# ------------------------------------------------------------ 1. chi-square tests
chi_rows <- lapply(seq_len(nrow(spec)), function(i) {
  f   <- spec$factor[i]
  tab <- table(df[[f]], df$is_attrited)
  ct  <- suppressWarnings(chisq.test(tab, correct = FALSE))
  k   <- min(dim(tab)) - 1
  data.frame(
    factor    = f,
    chi2      = unname(ct$statistic),
    dof       = unname(ct$parameter),
    p_value   = ct$p.value,
    cramers_v = sqrt(unname(ct$statistic) / (sum(tab) * k)),
    stringsAsFactors = FALSE
  )
})
chi <- do.call(rbind, chi_rows)
chi$p_adj_bh <- p.adjust(chi$p_value, method = "BH")
write.csv(chi, file.path(out_dir, "r_chi_square_tests.csv"), row.names = FALSE)

# ------------------------------------------------------------ 2. logistic regression
# Same explicit coding as Python: binary/ordinal as numeric, categorical as one
# dummy per non-reference level named "factor=level".
model_spec <- spec[spec$in_model == "1", ]
X <- data.frame(row.names = seq_len(nrow(df)))
for (i in seq_len(nrow(model_spec))) {
  f <- model_spec$factor[i]
  if (model_spec$kind[i] %in% c("binary", "ordinal")) {
    X[[f]] <- df[[f]]
  } else {
    lv <- sort(unique(df[[f]]))
    ref <- model_spec$reference[i]
    if (!(ref %in% lv)) stop(sprintf("reference '%s' not found in %s", ref, f))
    for (l in setdiff(lv, ref)) X[[paste0(f, "=", l)]] <- as.numeric(df[[f]] == l)
  }
}

fit_logit <- function(X, y) {
  safe <- make.names(names(X), unique = TRUE)
  lookup <- setNames(names(X), safe)
  d <- X; names(d) <- safe; d$.y <- y
  fit <- glm(.y ~ ., data = d, family = binomial(), control = glm.control(epsilon = 1e-12, maxit = 100))
  if (!fit$converged) stop("glm did not converge")
  list(fit = fit, lookup = lookup)
}

m <- fit_logit(X, df$is_attrited)
co <- summary(m$fit)$coefficients
co <- co[rownames(co) != "(Intercept)", , drop = FALSE]
z <- qnorm(1 - ALPHA / 2)
ors <- data.frame(
  term       = unname(m$lookup[rownames(co)]),
  coef       = co[, "Estimate"],
  std_err    = co[, "Std. Error"],
  odds_ratio = exp(co[, "Estimate"]),
  ci_low     = exp(co[, "Estimate"] - z * co[, "Std. Error"]),
  ci_high    = exp(co[, "Estimate"] + z * co[, "Std. Error"]),
  p_value    = co[, "Pr(>|z|)"],
  stringsAsFactors = FALSE, row.names = NULL
)
write.csv(ors, file.path(out_dir, "r_logit_odds_ratios.csv"), row.names = FALSE)

# ------------------------------------------------------------ 3. interaction LRT
Xi <- X
Xi[["works_overtime:early_tenure"]] <- X$works_overtime * as.numeric(df$years_at_company <= EARLY_TENURE_YEARS)
mi <- fit_logit(Xi, df$is_attrited)
lr <- as.numeric(2 * (logLik(mi$fit) - logLik(m$fit)))
inter <- data.frame(
  lr_statistic = lr,
  p_value = pchisq(lr, df = 1, lower.tail = FALSE),
  interaction_odds_ratio = exp(unname(coef(mi$fit)[make.names("works_overtime:early_tenure")])),
  log_likelihood_base = as.numeric(logLik(m$fit))
)
write.csv(inter, file.path(out_dir, "r_interaction_test.csv"), row.names = FALSE)

cat(sprintf("R replication: %d chi-square tests, %d odds ratios, interaction LRT p = %.4f\n",
            nrow(chi), nrow(ors), inter$p_value))
