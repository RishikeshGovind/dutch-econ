library(plumber)
library(jsonlite)
library(here)
library(stats)
library(dplyr)
library(tidyr)

#* @filter cors
cors <- function(req, res) {
  res$setHeader("Access-Control-Allow-Origin", "*")
  res$setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
  res$setHeader("Access-Control-Allow-Headers", "Content-Type")
  if (req$REQUEST_METHOD == "OPTIONS") return(res)
  plumber::forward()
}

# Load data once at startup
final_json <- readRDS(here("data", "final_json.rds"))
all_zones  <- c(final_json$Bezirk, final_json$Gemeinde)

# Load fiscal panel dataset
panel <- tryCatch(
  read.csv(here("data", "panel_dataset.csv"), stringsAsFactors = FALSE) |>
    mutate(gcd = sprintf("%05d", as.integer(gcd))),
  error = function(e) {
    message("panel_dataset.csv not found — fiscal endpoints unavailable")
    NULL
  }
)

# Pre-compute national fiscal averages per year (used for benchmarking)
if (!is.null(panel)) {
  national_avg <- panel |>
    group_by(year) |>
    summarise(
      nat_deficit_ratio    = median(deficit_ratio,    na.rm = TRUE),
      nat_exp_per_capita   = median(exp_per_capita,   na.rm = TRUE),
      nat_rev_per_capita   = median(rev_per_capita,   na.rm = TRUE),
      nat_exp_growth       = median(exp_growth,        na.rm = TRUE),
      nat_rev_growth       = median(rev_growth,        na.rm = TRUE),
      nat_pct_deficit      = mean(in_deficit,          na.rm = TRUE),
      nat_share_exp_admin              = median(share_exp_admin,              na.rm = TRUE),
      nat_share_exp_education_culture  = median(share_exp_education_culture,  na.rm = TRUE),
      nat_share_exp_social_welfare     = median(share_exp_social_welfare,     na.rm = TRUE),
      nat_share_exp_health             = median(share_exp_health,             na.rm = TRUE),
      nat_share_exp_infrastructure     = median(share_exp_infrastructure,     na.rm = TRUE),
      nat_share_exp_finance_debt       = median(share_exp_finance_debt,       na.rm = TRUE),
      .groups = "drop"
    )
}

# Simple rule-based fiscal risk score (0–100)
# Python/XGBoost will replace this with a trained model later.
compute_risk_score <- function(deficit_ratio, deficit_streak, exp_growth, rev_growth) {
  s <- 0
  # Deficit severity (0-40 pts)
  s <- s + pmin(40, pmax(0, deficit_ratio * 80))
  # Consecutive deficit years (0-30 pts)
  s <- s + pmin(30, deficit_streak * 6)
  # Expenditure growing faster than revenue (0-30 pts)
  growth_gap <- ifelse(is.na(exp_growth) | is.na(rev_growth), 0, exp_growth - rev_growth)
  s <- s + pmin(30, pmax(0, growth_gap * 60))
  round(pmin(100, pmax(0, s)), 1)
}

# Austria-wide baseline (population-weighted means)
at_raw    <- final_json$`Austria Total`
var_names <- names(unlist(at_raw, use.names = TRUE))
at_vector <- setNames(
  as.numeric(unlist(at_raw, use.names = TRUE)),
  var_names
)

# ---- Domain patterns ----
# Keys match the domain group names set in fetch_austria_data.R VARIABLE_MAP.
# Used to identify which columns belong to each thematic block.
DOMAINS <- list(
  Altersstruktur    = "^Altersstruktur\\.",
  Arbeitsmarkt      = "^Arbeitsmarkt\\.",
  Bildung           = "^Bildung\\.",
  Migration         = "^Migration\\.",
  Haushalte         = "^Haushalte\\."
)

# All indicator data is already in % / rate / index form, so no
# within-domain normalisation is needed — just return the matrix.
make_pct_matrix <- function(mat) mat

# ---- Encoding fix ----
# Zone names in the RDS were saved with UTF-8 bytes stored without an encoding
# mark, causing double-encoding when serialised. Decode via latin1 and re-mark.
fix_enc <- function(x) {
  if (!is.character(x) || length(x) == 0) return(x)
  y <- iconv(x, from = "UTF-8", to = "latin1")
  Encoding(y) <- "UTF-8"
  y
}

# ---- Zone label helper ----
label_map <- lapply(all_zones, function(z) {
  name <- z[["Gemeindename"]]
  if (is.null(name)) return(NULL)
  fix_enc(as.character(name[[1]]))
})

# ---- Feature matrix (one row per zone, one col per indicator) ----
build_zone_matrix <- function(sel_zones) {
  zone_vecs <- lapply(sel_zones, function(z) {
    flat <- unlist(z[names(z) %in% names(at_raw)], use.names = TRUE)
    v    <- setNames(numeric(length(var_names)), var_names)
    v[names(flat)] <- as.numeric(flat)
    v
  })
  mat <- do.call(rbind, zone_vecs)
  colnames(mat) <- var_names
  mat
}

# ---- Cluster interpretation ----
# Compares a cluster centroid against the Austria-wide baseline and
# returns the most distinctive socioeconomic drivers with policy context.
interpret_cluster <- function(pct_row, at_vector, top_n = 3) {

  pct_over <- mapply(function(x, y) {
    if (is.na(y) || y <= 0) return(NA_real_)
    (x - y) / y
  }, x = pct_row, y = at_vector)
  names(pct_over) <- names(pct_row)
  pct_over <- pct_over[!is.na(pct_over)]

  if (any(pct_over > 0, na.rm = TRUE)) {
    ppos <- pct_over[pct_over > 0]
    zpos <- if (length(ppos) > 1 && sd(ppos, na.rm = TRUE) > 0) {
      (ppos - mean(ppos, na.rm = TRUE)) / sd(ppos, na.rm = TRUE)
    } else {
      setNames(rep(0, length(ppos)), names(ppos))
    }
    sel <- head(names(sort(zpos, decreasing = TRUE)), top_n)
    z   <- zpos[sel]
  } else {
    zall <- if (sd(pct_over, na.rm = TRUE) > 0) {
      (pct_over - mean(pct_over, na.rm = TRUE)) / sd(pct_over, na.rm = TRUE)
    } else {
      setNames(rep(0, length(pct_over)), names(pct_over))
    }
    sel <- head(names(sort(abs(zall), decreasing = TRUE)), top_n)
    z   <- zall[sel]
  }
  pval <- 2 * (1 - pnorm(abs(z)))

  drivers <- lapply(seq_along(sel), function(i) list(
    variable = sel[i],
    pct_over = round(pct_over[sel[i]] * 100, 1),
    z        = round(z[i], 2),
    p        = signif(pval[i], 2)
  ))

  # Austrian policy trait map
  trait_map <- list(
    aging   = list(
      trait         = "Aging population",
      challenges    = c("Healthcare access", "Pension pressure",
                        "Social isolation"),
      opportunities = "Silver economy, Pflegedaheim, community care"
    ),
    youth   = list(
      trait         = "Young population",
      challenges    = c("School & childcare capacity",
                        "Youth unemployment risk"),
      opportunities = "Education investment, apprenticeship expansion"
    ),
    unempl  = list(
      trait         = "High unemployment",
      challenges    = c("Income poverty", "Social exclusion"),
      opportunities = "AMS active labour programs, Kurzarbeit schemes"
    ),
    empl    = list(
      trait         = "High employment rate",
      challenges    = "Skills matching, in-commuter pressure",
      opportunities = "Workforce retention, local enterprise support"
    ),
    edu_low = list(
      trait         = "Low tertiary education share",
      challenges    = c("Labour market transition risk",
                        "Digital skills gap"),
      opportunities = "BFI, Lehre mit Matura, AMS upskilling"
    ),
    commute = list(
      trait         = "High out-commuter share",
      challenges    = c("Local services underfunded",
                        "Transport dependency"),
      opportunities = "Remote-work infrastructure, ÖPNV investment"
    ),
    migrant = list(
      trait         = "High foreign-citizen share",
      challenges    = c("Integration services", "Language barriers"),
      opportunities = "Integration funds, multilingual services"
    ),
    hh_size = list(
      trait         = "Large average household size",
      challenges    = "Affordable housing pressure",
      opportunities = "Social housing expansion, family support"
    ),
    rural   = list(
      trait         = "Rural structural weakness",
      challenges    = c("Outmigration", "Service accessibility"),
      opportunities = "LEADER program, Breitbandausbau, ÖPNV"
    )
  )

  find_dim <- function(v) {
    if (grepl("Über 65", v))                       "aging"
    else if (grepl("Unter 15", v))                 "youth"
    else if (grepl("Arbeitslosenquote", v))        "unempl"
    else if (grepl("Beschäftigungsquote", v))      "empl"
    else if (grepl("Tertiärbildung", v))           "edu_low"
    else if (grepl("Auspendler", v))               "commute"
    else if (grepl("Ausländische", v))             "migrant"
    else if (grepl("Haushaltsgröße", v))           "hh_size"
    else NA_character_
  }

  dims <- sapply(sel, find_dim, USE.NAMES = FALSE)
  ct <- ch <- op <- character()
  for (i in seq_along(dims)) {
    d <- dims[i]
    if (!is.na(d) && !is.null(trait_map[[d]])) {
      m  <- trait_map[[d]]
      ct <- c(ct, m$trait)
      ch <- c(ch, m$challenges)
      op <- c(op, m$opportunities)
    } else {
      ct <- c(ct, sel[i])
    }
  }

  list(
    drivers       = drivers,
    common_traits = unique(ct),
    challenges    = unique(ch),
    opportunities = unique(op)
  )
}


# ============================================================
# Endpoints
# ============================================================

#* @get /cluster_typology
#* @serializer json
#* @param ids Comma-separated Gemeinde GKZ or Bezirk codes
cluster_typology <- function(ids = "", res) {
  sel_ids <- strsplit(ids, ",", fixed = TRUE)[[1]]
  if (length(sel_ids) < 3) {
    res$status <- 400
    return(list(error = "Select at least 3 zones for clustering."))
  }

  sel_zones <- all_zones[names(all_zones) %in% sel_ids]
  if (length(sel_zones) < 3) {
    res$status <- 400
    return(list(error = sprintf(
      "Only %d valid zones found — need at least 3.", length(sel_zones)
    )))
  }

  mat        <- build_zone_matrix(sel_zones)
  scaled_mat <- scale(mat, center = TRUE, scale = TRUE)
  scaled_mat[is.nan(scaled_mat)] <- 0

  k <- min(3L, nrow(scaled_mat) - 1L)
  k <- max(k, 2L)
  set.seed(123)
  km <- kmeans(scaled_mat, centers = k, nstart = 25)

  assignments <- data.frame(
    zone    = names(sel_zones),
    cluster = km$cluster,
    stringsAsFactors = FALSE
  )

  # Unscale centroids back to original indicator space
  centers_raw <- sweep(
    km$centers, 2, attr(scaled_mat, "scaled:scale"), FUN = "*"
  )
  centroids <- sweep(
    centers_raw, 2, attr(scaled_mat, "scaled:center"), FUN = "+"
  )

  summary_out <- list()
  for (cl in sort(unique(assignments$cluster))) {
    members <- assignments$zone[assignments$cluster == cl]
    labels  <- vapply(members, function(id) {
      lab <- label_map[[id]]
      if (is.null(lab) || length(lab) == 0) return(id)
      as.character(lab[[1]])
    }, FUN.VALUE = "")

    interp <- interpret_cluster(centroids[cl, ], at_vector)

    summary_out[[paste0("Cluster_", cl)]] <- list(
      count         = length(members),
      zones         = unname(labels),
      drivers       = interp$drivers,
      common_traits = interp$common_traits,
      challenges    = interp$challenges,
      opportunities = interp$opportunities
    )
  }

  profiles         <- as.data.frame(centroids)
  profiles$cluster <- seq_len(nrow(profiles))

  list(
    summary     = summary_out,
    assignments = assignments,
    profiles    = profiles,
    at_profile  = as.list(at_vector)
  )
}


#* @get /cluster_plot_data
#* @serializer json
#* @param ids Comma-separated zone codes
cluster_plot_data <- function(ids = "", res) {
  sel_ids   <- strsplit(ids, ",", fixed = TRUE)[[1]]
  sel_zones <- all_zones[names(all_zones) %in% sel_ids]
  if (length(sel_zones) < 3) {
    res$status <- 400
    return(list(error = "Need at least 3 zones for PCA/clustering."))
  }

  mat        <- build_zone_matrix(sel_zones)
  scaled_mat <- scale(mat, center = TRUE, scale = TRUE)

  k  <- min(3, nrow(scaled_mat))
  set.seed(123)
  km  <- kmeans(scaled_mat, centers = k, nstart = 25)
  pca <- prcomp(scaled_mat, center = FALSE, scale. = FALSE)

  pts         <- as.data.frame(pca$x[, 1:2])
  pts$zone    <- rownames(mat)
  pts$cluster <- km$cluster

  centroids_proj         <- as.data.frame(
    predict(pca, newdata = km$centers)[, 1:2]
  )
  centroids_proj$cluster <- seq_len(nrow(centroids_proj))

  var_exp  <- (pca$sdev^2) / sum(pca$sdev^2)
  rotation <- pca$rotation[, 1:2, drop = FALSE]

  make_loadings <- function(pc) {
    vec      <- rotation[, pc]
    top_vars <- names(head(sort(abs(vec), decreasing = TRUE), 10))
    total_sq <- sum(rotation[, pc]^2)
    lapply(top_vars, function(v) list(
      variable     = v,
      loading      = as.numeric(vec[v]),
      contribution = as.numeric((vec[v]^2) / total_sq)
    ))
  }

  list(
    points             = pts,
    centroids          = centroids_proj,
    variance_explained = var_exp[1:2],
    loadings           = list(PC1 = make_loadings(1), PC2 = make_loadings(2))
  )
}


#* @get /variable_relationship_heatmap
#* @serializer unboxedJSON
#* @param ids    Comma-separated zone codes
#* @param method "pearson" (default) or "spearman"
variable_relationship_heatmap <- function(ids = "", method = "pearson") {
  sel_ids   <- strsplit(ids, ",", fixed = TRUE)[[1]]
  sel_zones <- all_zones[names(all_zones) %in% sel_ids]
  if (length(sel_zones) < 3) {
    return(list(error = "Need at least 3 zones."))
  }

  mat    <- build_zone_matrix(sel_zones)
  method <- if (tolower(method) %in% c("pearson", "spearman")) {
    tolower(method)
  } else {
    "pearson"
  }

  vars   <- colnames(mat)
  n      <- length(vars)
  corr_m <- matrix(NA_real_, n, n, dimnames = list(vars, vars))
  pval_m <- matrix(NA_real_, n, n, dimnames = list(vars, vars))

  for (i in seq_len(n)) {
    for (j in i:n) {
      ok <- !is.na(mat[, i]) & !is.na(mat[, j])
      if (sum(ok) < 3) next
      test <- tryCatch(
        cor.test(mat[ok, i], mat[ok, j], method = method),
        error = function(e) NULL
      )
      if (!is.null(test)) {
        corr_m[i, j] <- corr_m[j, i] <- unname(test$estimate)
        pval_m[i, j] <- pval_m[j, i] <- unname(test$p.value)
      }
    }
  }

  signif_m <- matrix("", n, n, dimnames = list(vars, vars))
  signif_m[pval_m < 0.001] <- "***"
  signif_m[pval_m >= 0.001 & pval_m < 0.01] <- "**"
  signif_m[pval_m >= 0.01  & pval_m < 0.05] <- "*"

  dist_m <- as.dist(1 - abs(replace(corr_m, is.na(corr_m), 0)))
  hc     <- hclust(dist_m, method = "average")
  ord    <- hc$labels[hc$order]

  to_list <- function(m) {
    lapply(rownames(m), function(r) {
      setNames(as.list(m[r, ]), colnames(m))
    }) |> setNames(rownames(m))
  }

  list(
    variables        = ord,
    corr             = to_list(corr_m[ord, ord]),
    pvals            = to_list(pval_m[ord, ord]),
    signif           = to_list(signif_m[ord, ord]),
    clustering_order = ord,
    method           = method,
    n_zones          = nrow(mat)
  )
}


#* @get /zone_timeseries
#* @serializer json
#* @param id Single Gemeinde GKZ code
#* @param variable One of: ALQ_15PLUS, EWTQ_15BIS64, EDU_15_TER,
#*   EDU_15_SEK, BEV_ABSOLUT, AUSL_STAATSB, AUSPENDLER, HH_SIZE
zone_timeseries <- function(id = "", variable = "ALQ_15PLUS", res) {
  if (id == "") {
    res$status <- 400
    return(list(error = "Provide a zone id."))
  }
  ts_data <- final_json$timeseries[[id]]
  if (is.null(ts_data)) {
    res$status <- 404
    return(list(error = paste("No time series for zone:", id)))
  }
  years  <- as.integer(names(ts_data))
  values <- sapply(ts_data, function(yr) {
    v <- yr[[variable]]
    if (is.null(v)) NA_real_ else as.numeric(v)
  })
  list(
    zone     = id,
    variable = variable,
    years    = years,
    values   = unname(values)
  )
}


# ============================================================
# Fiscal endpoints (powered by panel_dataset.csv)
# ============================================================

#* @get /fiscal_profile
#* @serializer json
#* @param ids Comma-separated Gemeinde GKZ codes
#* @param year Year to profile (default: most recent available)
fiscal_profile <- function(ids = "", year = "", res) {
  if (is.null(panel)) {
    res$status <- 503
    return(list(error = "panel_dataset.csv not loaded."))
  }

  sel_ids <- strsplit(ids, ",", fixed = TRUE)[[1]]
  sel_ids <- sprintf("%05d", as.integer(sel_ids))

  yr <- if (year == "") max(panel$year, na.rm = TRUE) else as.integer(year)

  zone_data <- panel |>
    filter(gcd %in% sel_ids, year == yr)

  if (nrow(zone_data) == 0) {
    res$status <- 404
    return(list(error = sprintf("No data for selected zones in year %d.", yr)))
  }

  nat <- national_avg |> filter(year == yr)

  profiles <- lapply(seq_len(nrow(zone_data)), function(i) {
    z <- zone_data[i, ]
    risk <- compute_risk_score(z$deficit_ratio, z$deficit_streak,
                               z$exp_growth,    z$rev_growth)
    list(
      gcd              = z$gcd,
      year             = z$year,
      bundesland       = z$bundesland,
      settlement_class = z$settlement_class,
      urban_rural      = z$urban_rural,
      population       = z$population,
      fiscal = list(
        total_expenditure  = z$total_expenditure,
        total_revenue      = z$total_revenue,
        fiscal_balance     = z$fiscal_balance,
        deficit_ratio      = round(z$deficit_ratio, 4),
        in_deficit         = z$in_deficit,
        deficit_streak     = z$deficit_streak,
        exp_per_capita     = round(z$exp_per_capita, 1),
        rev_per_capita     = round(z$rev_per_capita, 1),
        balance_per_capita = round(z$balance_per_capita, 1),
        exp_growth         = round(z$exp_growth, 4),
        rev_growth         = round(z$rev_growth, 4)
      ),
      spending_shares = list(
        admin             = round(z$share_exp_admin, 4),
        education_culture = round(z$share_exp_education_culture, 4),
        social_welfare    = round(z$share_exp_social_welfare, 4),
        health            = round(z$share_exp_health, 4),
        infrastructure    = round(z$share_exp_infrastructure, 4),
        finance_debt      = round(z$share_exp_finance_debt, 4),
        economy           = round(z$share_exp_economy, 4),
        utilities         = round(z$share_exp_utilities, 4)
      ),
      risk_score = risk
    )
  })

  nat_profile <- if (nrow(nat) > 0) list(
    deficit_ratio          = round(nat$nat_deficit_ratio, 4),
    exp_per_capita         = round(nat$nat_exp_per_capita, 1),
    rev_per_capita         = round(nat$nat_rev_per_capita, 1),
    pct_municipalities_in_deficit = round(nat$nat_pct_deficit * 100, 1),
    spending_shares = list(
      admin             = round(nat$nat_share_exp_admin, 4),
      education_culture = round(nat$nat_share_exp_education_culture, 4),
      social_welfare    = round(nat$nat_share_exp_social_welfare, 4),
      health            = round(nat$nat_share_exp_health, 4),
      infrastructure    = round(nat$nat_share_exp_infrastructure, 4),
      finance_debt      = round(nat$nat_share_exp_finance_debt, 4)
    )
  ) else NULL

  list(year = yr, zones = profiles, national_benchmark = nat_profile)
}


#* @get /fiscal_timeseries
#* @serializer json
#* @param ids  Comma-separated Gemeinde GKZ codes
#* @param metric One of: deficit_ratio, exp_per_capita, rev_per_capita,
#*   balance_per_capita, exp_growth, rev_growth, deficit_streak,
#*   share_exp_education_culture, share_exp_social_welfare,
#*   share_exp_infrastructure, share_exp_finance_debt
fiscal_timeseries <- function(ids = "", metric = "deficit_ratio", res) {
  if (is.null(panel)) {
    res$status <- 503
    return(list(error = "panel_dataset.csv not loaded."))
  }

  allowed <- c("deficit_ratio", "exp_per_capita", "rev_per_capita",
               "balance_per_capita", "exp_growth", "rev_growth",
               "deficit_streak", "share_exp_education_culture",
               "share_exp_social_welfare", "share_exp_infrastructure",
               "share_exp_finance_debt", "total_expenditure", "total_revenue")

  if (!metric %in% allowed) {
    res$status <- 400
    return(list(error = paste("Invalid metric. Choose one of:", paste(allowed, collapse = ", "))))
  }

  sel_ids <- sprintf("%05d", as.integer(strsplit(ids, ",", fixed = TRUE)[[1]]))

  zone_ts <- panel |>
    filter(gcd %in% sel_ids) |>
    select(gcd, year, bundesland, settlement_class, value = all_of(metric)) |>
    arrange(gcd, year)

  if (nrow(zone_ts) == 0) {
    res$status <- 404
    return(list(error = "No data found for selected zones."))
  }

  # National median per year
  nat_ts <- national_avg |>
    select(year, nat_value = any_of(paste0("nat_", metric))) |>
    filter(!is.na(nat_value))

  # Per-zone series
  series <- lapply(unique(zone_ts$gcd), function(id) {
    z <- zone_ts |> filter(gcd == id)
    list(
      gcd             = id,
      bundesland      = z$bundesland[1],
      settlement_class = z$settlement_class[1],
      years           = z$year,
      values          = round(z$value, 4)
    )
  })

  list(
    metric           = metric,
    years_available  = sort(unique(zone_ts$year)),
    series           = series,
    national_median  = if (nrow(nat_ts) > 0) list(
      years  = nat_ts$year,
      values = round(nat_ts$nat_value, 4)
    ) else NULL
  )
}


#* @get /fiscal_clustering
#* @serializer json
#* @param ids Comma-separated Gemeinde GKZ codes
#* @param year Year to use for clustering (default: most recent)
#* @param k   Number of clusters (2–6, default: 3)
fiscal_clustering <- function(ids = "", year = "", k = "3", res) {
  if (is.null(panel)) {
    res$status <- 503
    return(list(error = "panel_dataset.csv not loaded."))
  }

  sel_ids <- sprintf("%05d", as.integer(strsplit(ids, ",", fixed = TRUE)[[1]]))
  yr      <- if (year == "") max(panel$year, na.rm = TRUE) else as.integer(year)
  k_val   <- min(6, max(2, as.integer(k)))

  fiscal_features <- c("deficit_ratio", "exp_per_capita", "rev_per_capita",
                       "share_exp_admin", "share_exp_education_culture",
                       "share_exp_social_welfare", "share_exp_health",
                       "share_exp_infrastructure", "share_exp_finance_debt",
                       "exp_growth", "rev_growth", "deficit_streak")

  zone_data <- panel |>
    filter(gcd %in% sel_ids, year == yr) |>
    select(gcd, bundesland, settlement_class, urban_rural,
           all_of(fiscal_features))

  zone_data <- zone_data[complete.cases(zone_data[, fiscal_features]), ]

  if (nrow(zone_data) < k_val) {
    res$status <- 400
    return(list(error = sprintf(
      "Only %d zones with complete data — need at least %d for k=%d.",
      nrow(zone_data), k_val, k_val
    )))
  }

  mat        <- as.matrix(zone_data[, fiscal_features])
  rownames(mat) <- zone_data$gcd
  scaled_mat <- scale(mat)

  set.seed(42)
  km <- kmeans(scaled_mat, centers = k_val, nstart = 25)

  zone_data$cluster <- km$cluster

  # Cluster summary: median of each feature per cluster
  cluster_profiles <- lapply(sort(unique(km$cluster)), function(cl) {
    members <- zone_data |> filter(cluster == cl)
    meds    <- round(colMeans(mat[members$gcd, , drop = FALSE], na.rm = TRUE), 4)

    # Characterise: dominant spending category
    spend_cols  <- grep("^share_exp_", names(meds), value = TRUE)
    top_spend   <- sub("share_exp_", "", names(which.max(meds[spend_cols])))
    avg_risk     <- round(mean(compute_risk_score(
      members$deficit_ratio, members$deficit_streak,
      members$exp_growth, members$rev_growth
    ), na.rm = TRUE), 1)

    zone_risks <- compute_risk_score(
      members$deficit_ratio, members$deficit_streak,
      members$exp_growth,    members$rev_growth
    )
    list(
      cluster          = cl,
      n_zones          = nrow(members),
      gcds             = members$gcd,
      avg_risk_score   = avg_risk,
      top_spending_cat = top_spend,
      fiscal_profile   = as.list(meds),
      bundesland_dist  = as.list(table(members$bundesland)),
      settlement_dist  = as.list(table(members$settlement_class)),
      zones = lapply(seq_len(nrow(members)), function(j) list(
        gcd              = members$gcd[j],
        bundesland       = members$bundesland[j],
        settlement_class = members$settlement_class[j],
        urban_rural      = members$urban_rural[j],
        deficit_ratio    = round(members$deficit_ratio[j], 4),
        exp_per_capita   = round(members$exp_per_capita[j], 0),
        deficit_streak   = members$deficit_streak[j],
        risk_score       = round(zone_risks[j], 1)
      ))
    )
  })

  assignments <- data.frame(
    gcd             = zone_data$gcd,
    cluster         = zone_data$cluster,
    bundesland      = zone_data$bundesland,
    settlement_class = zone_data$settlement_class,
    urban_rural     = zone_data$urban_rural,
    risk_score      = compute_risk_score(
      zone_data$deficit_ratio, zone_data$deficit_streak,
      zone_data$exp_growth,    zone_data$rev_growth
    ),
    stringsAsFactors = FALSE
  )

  list(
    year        = yr,
    k           = k_val,
    n_zones     = nrow(zone_data),
    assignments = assignments,
    profiles    = cluster_profiles
  )
}


#* @get /fiscal_risk_summary
#* @serializer json
#* @param ids Comma-separated Gemeinde GKZ codes
fiscal_risk_summary <- function(ids = "", res) {
  if (is.null(panel)) {
    res$status <- 503
    return(list(error = "panel_dataset.csv not loaded."))
  }

  sel_ids <- sprintf("%05d", as.integer(strsplit(ids, ",", fixed = TRUE)[[1]]))
  latest  <- max(panel$year, na.rm = TRUE)

  zone_data <- panel |>
    filter(gcd %in% sel_ids, year == latest)

  if (nrow(zone_data) == 0) {
    res$status <- 404
    return(list(error = "No data found for selected zones."))
  }

  # Trend: is the deficit_ratio improving or deteriorating over last 3 years?
  trend_data <- panel |>
    filter(gcd %in% sel_ids, year >= (latest - 2)) |>
    group_by(gcd) |>
    summarise(
      trend = if (n() >= 2) {
        m <- lm(deficit_ratio ~ year, data = cur_data())
        sign(coef(m)["year"])
      } else NA_real_,
      .groups = "drop"
    )

  result <- zone_data |>
    left_join(trend_data, by = "gcd") |>
    mutate(
      risk_score     = compute_risk_score(deficit_ratio, deficit_streak,
                                          exp_growth, rev_growth),
      risk_category  = case_when(
        risk_score >= 60 ~ "High",
        risk_score >= 30 ~ "Medium",
        TRUE             ~ "Low"
      ),
      trend_direction = case_when(
        trend > 0  ~ "Deteriorating",
        trend < 0  ~ "Improving",
        TRUE       ~ "Stable"
      )
    ) |>
    arrange(desc(risk_score))

  # National percentile rank for each zone's deficit_ratio
  all_latest <- panel |> filter(year == latest) |> pull(deficit_ratio)

  zones_out <- lapply(seq_len(nrow(result)), function(i) {
    z <- result[i, ]
    pct_rank <- round(mean(all_latest <= z$deficit_ratio, na.rm = TRUE) * 100, 1)
    list(
      gcd              = z$gcd,
      bundesland       = z$bundesland,
      settlement_class = z$settlement_class,
      urban_rural      = z$urban_rural,
      year             = latest,
      risk_score       = z$risk_score,
      risk_category    = z$risk_category,
      trend_direction  = z$trend_direction,
      deficit_ratio    = round(z$deficit_ratio, 4),
      deficit_streak   = z$deficit_streak,
      exp_per_capita   = round(z$exp_per_capita, 1),
      rev_per_capita   = round(z$rev_per_capita, 1),
      national_percentile = pct_rank
    )
  })

  nat <- national_avg |> filter(year == latest)

  list(
    year   = latest,
    note   = "risk_score is rule-based (0-100). ML model prediction available via Python /predict_distress endpoint.",
    zones  = zones_out,
    national_context = list(
      median_deficit_ratio        = round(nat$nat_deficit_ratio, 4),
      pct_municipalities_in_deficit = round(nat$nat_pct_deficit * 100, 1)
    )
  )
}
