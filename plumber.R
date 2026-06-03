library(plumber)
library(jsonlite)
library(here)
library(stats)
library(dplyr)
library(tidyr)
library(cluster)

#* @filter cors
cors <- function(req, res) {
  res$setHeader("Access-Control-Allow-Origin",  "*")
  res$setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
  res$setHeader("Access-Control-Allow-Headers", "Content-Type")
  if (req$REQUEST_METHOD == "OPTIONS") return(res)
  plumber::forward()
}

# ── Load data ──────────────────────────────────────────────────────────────────
final_json <- readRDS(here("data", "final_json.rds"))
all_zones  <- final_json$Kommune   # 98 municipalities keyed by 4-digit DAWA code

# ── National baseline (Denmark Total) ─────────────────────────────────────────
dk_raw <- final_json[["Denmark Total"]]

NUMERIC_DOMAINS <- c(
  "AgeStructure", "LabourMarket", "Economy", "Education",
  "Migration", "Ancestry", "Housing", "Safety", "Welfare",
  "PopulationDynamics", "Financial", "Health", "Businesses", "Vehicles",
  "IndustrySectors", "GreenEnergy", "ClimateBaseline", "GreenTransition"
)

flatten_zone <- function(z) {
  parts <- lapply(NUMERIC_DOMAINS, function(d) {
    dom <- z[[d]]
    if (is.null(dom) || !is.list(dom)) return(NULL)
    sapply(dom, function(v) {
      if (is.null(v) || length(v) == 0) NA_real_ else as.numeric(v[[1]])
    })
  })
  names(parts) <- NUMERIC_DOMAINS
  parts <- Filter(Negate(is.null), parts)
  unlist(parts, use.names = TRUE)
}

at_vector <- flatten_zone(dk_raw)
var_names  <- names(at_vector)

# ── Build zone feature matrix ──────────────────────────────────────────────────
build_zone_matrix <- function(sel_zones) {
  zone_vecs <- lapply(sel_zones, function(z) {
    flat <- flatten_zone(z)
    v    <- setNames(numeric(length(var_names)), var_names)
    v[names(flat)] <- flat
    v
  })
  mat           <- do.call(rbind, zone_vecs)
  colnames(mat) <- var_names
  mat
}

# ── Clustering helpers ────────────────────────────────────────────────────────

# Impute each column's NAs with that column's median, then centre/scale.
# Zero-variance columns (sd=0) produce NaN after scale(); those are zeroed out.
prep_scaled_matrix <- function(mat) {
  for (j in seq_len(ncol(mat))) {
    na_idx <- is.na(mat[, j])
    if (any(na_idx)) {
      col_med <- median(mat[, j], na.rm = TRUE)
      mat[na_idx, j] <- if (is.finite(col_med)) col_med else 0
    }
  }
  sc <- scale(mat, center = TRUE, scale = TRUE)
  sc[!is.finite(sc)] <- 0   # guard for zero-variance columns
  sc
}

# Try k = 2..min(8, n-1) and return the k with the highest mean silhouette width.
select_k_silhouette <- function(scaled_mat) {
  n     <- nrow(scaled_mat)
  k_max <- min(8L, n - 1L)
  if (k_max < 2L) return(2L)
  d <- dist(scaled_mat)
  scores <- vapply(2L:k_max, function(k_try) {
    set.seed(123)
    km_try <- kmeans(scaled_mat, centers = k_try, nstart = 25)
    mean(silhouette(km_try$cluster, d)[, "sil_width"])
  }, numeric(1))
  (2L:k_max)[which.max(scores)]
}

# ── Danish cluster interpretation ─────────────────────────────────────────────
trait_map <- list(
  aging   = list(
    trait         = "Aging population",
    challenges    = c("Eldercare cost pressure", "Healthcare demand", "Labour shortage"),
    opportunities = "Silver economy, home-care expansion, senior housing investment"
  ),
  youth   = list(
    trait         = "Young population",
    challenges    = c("School & childcare capacity", "Youth unemployment risk"),
    opportunities = "Education investment, EUD apprenticeship expansion"
  ),
  unempl  = list(
    trait         = "High unemployment",
    challenges    = c("Income poverty", "Welfare dependency", "Social exclusion"),
    opportunities = "Aktiveringsindsats, flexjob schemes, job rotation"
  ),
  empl    = list(
    trait         = "High employment",
    challenges    = "Skills matching, in-commuter pressure on local services",
    opportunities = "Workforce retention, local enterprise support"
  ),
  edu_low = list(
    trait         = "Low tertiary education share",
    challenges    = c("Labour market transition risk", "Digital skills gap"),
    opportunities = "VEU continuing education, EUD reform, municipal upskilling funds"
  ),
  commute = list(
    trait         = "High out-commuter share",
    challenges    = c("Local services underfunded", "Transport dependency"),
    opportunities = "Remote-work infrastructure, local job creation"
  ),
  migrant = list(
    trait         = "High foreign-citizen share",
    challenges    = c("Integration services", "Language barriers"),
    opportunities = "Integrationsprogrammer, multilingual public services"
  ),
  welfare = list(
    trait         = "High welfare dependency",
    challenges    = c("Municipal fiscal strain", "Social mobility barriers"),
    opportunities = "Aktiveringsindsats, boligsociale indsatser, social investment"
  ),
  rural   = list(
    trait         = "Rural structural challenge",
    challenges    = c("Population outmigration", "Service accessibility gaps"),
    opportunities = "Landdistriktsudvikling, broadband rollout, remote public services"
  )
)

find_dim <- function(v) {
  if      (grepl("Over 65",             v, ignore.case = TRUE)) "aging"
  else if (grepl("Under 15",            v, ignore.case = TRUE)) "youth"
  else if (grepl("Unemployment",        v, ignore.case = TRUE)) "unempl"
  else if (grepl("Employment rate",     v, ignore.case = TRUE)) "empl"
  else if (grepl("Tertiary",            v, ignore.case = TRUE)) "edu_low"
  else if (grepl("Out-commuter",        v, ignore.case = TRUE)) "commute"
  else if (grepl("Foreign|Immigrant",   v, ignore.case = TRUE)) "migrant"
  else if (grepl("Welfare dependency",  v, ignore.case = TRUE)) "welfare"
  else NA_character_
}

interpret_cluster <- function(pct_row, at_vec, top_n = 3) {
  pct_over <- mapply(function(x, y) {
    if (is.na(y) || y <= 0) return(NA_real_)
    (x - y) / y
  }, x = pct_row, y = at_vec)
  names(pct_over) <- names(pct_row)
  pct_over <- pct_over[!is.na(pct_over)]

  if (any(pct_over > 0, na.rm = TRUE)) {
    ppos <- pct_over[pct_over > 0]
    zpos <- if (length(ppos) > 1 && sd(ppos, na.rm = TRUE) > 0)
      (ppos - mean(ppos, na.rm = TRUE)) / sd(ppos, na.rm = TRUE)
    else setNames(rep(0, length(ppos)), names(ppos))
    sel <- head(names(sort(zpos, decreasing = TRUE)), top_n)
    z   <- zpos[sel]
  } else {
    zall <- if (sd(pct_over, na.rm = TRUE) > 0)
      (pct_over - mean(pct_over, na.rm = TRUE)) / sd(pct_over, na.rm = TRUE)
    else setNames(rep(0, length(pct_over)), names(pct_over))
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


# ══════════════════════════════════════════════════════════════════════════════
# Endpoints
# ══════════════════════════════════════════════════════════════════════════════

#* @get /health
#* @serializer unboxedJSON
health <- function() {
  list(
    status         = "ok",
    n_zones        = length(all_zones),
    n_features     = length(var_names),
    has_timeseries = !is.null(final_json$timeseries)
  )
}


#* @get /cluster_typology
#* @serializer unboxedJSON
#* @param ids Comma-separated 4-digit kommune codes (e.g. "0101,0147,0751")
cluster_typology <- function(ids = "", res) {
  tryCatch({
  sel_ids   <- trimws(strsplit(ids, ",", fixed = TRUE)[[1]])
  if (length(sel_ids) < 3) {
    res$status <- 400
    return(list(error = "Select at least 3 zones for clustering."))
  }

  sel_zones <- all_zones[names(all_zones) %in% sel_ids]
  if (length(sel_zones) < 3) {
    res$status <- 400
    return(list(error = sprintf(
      "Only %d valid zones found (need ≥ 3). Sent: %s. Keys sample: %s",
      length(sel_zones),
      paste(sel_ids[1:min(3,length(sel_ids))], collapse=","),
      paste(names(all_zones)[1:min(3,length(all_zones))], collapse=",")
    )))
  }

  mat        <- build_zone_matrix(sel_zones)
  scaled_mat <- prep_scaled_matrix(mat)
  k          <- select_k_silhouette(scaled_mat)
  set.seed(123)
  km         <- kmeans(scaled_mat, centers = k, nstart = 25)

  assignments <- data.frame(
    zone    = names(sel_zones),
    cluster = km$cluster,
    stringsAsFactors = FALSE
  )

  centers_raw <- sweep(km$centers,   2, attr(scaled_mat, "scaled:scale"), FUN = "*")
  centroids   <- sweep(centers_raw,  2, attr(scaled_mat, "scaled:center"), FUN = "+")

  summary_out <- list()
  for (cl in sort(unique(assignments$cluster))) {
    members <- assignments$zone[assignments$cluster == cl]
    interp  <- interpret_cluster(centroids[cl, ], at_vector)

    summary_out[[paste0("Cluster_", cl)]] <- list(
      count         = length(members),
      zones         = unname(members),
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
    dk_profile  = as.list(at_vector),
    k_selected  = k
  )
  }, error = function(e) {
    res$status <- 500
    list(error = conditionMessage(e))
  })
}


#* @get /cluster_plot_data
#* @serializer json
#* @param ids Comma-separated zone codes
cluster_plot_data <- function(ids = "", res) {
  sel_ids   <- trimws(strsplit(ids, ",", fixed = TRUE)[[1]])
  sel_zones <- all_zones[names(all_zones) %in% sel_ids]
  if (length(sel_zones) < 3) {
    res$status <- 400
    return(list(error = "Need at least 3 zones for PCA/clustering."))
  }

  mat        <- build_zone_matrix(sel_zones)
  scaled_mat <- prep_scaled_matrix(mat)
  k          <- select_k_silhouette(scaled_mat)
  set.seed(123)
  km         <- kmeans(scaled_mat, centers = k, nstart = 25)
  pca <- prcomp(scaled_mat, center = FALSE, scale. = FALSE)

  pts         <- as.data.frame(pca$x[, 1:2])
  pts$zone    <- rownames(mat)
  pts$cluster <- km$cluster

  centroids_proj         <- as.data.frame(predict(pca, newdata = km$centers)[, 1:2])
  centroids_proj$cluster <- seq_len(nrow(centroids_proj))

  var_exp  <- (pca$sdev^2) / sum(pca$sdev^2)
  rotation <- pca$rotation[, 1:2, drop = FALSE]

  make_loadings <- function(pc) {
    vec      <- rotation[, pc]
    top_vars <- names(head(sort(abs(vec), decreasing = TRUE), 8))
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
  sel_ids   <- trimws(strsplit(ids, ",", fixed = TRUE)[[1]])
  sel_zones <- all_zones[names(all_zones) %in% sel_ids]
  if (length(sel_zones) < 3) {
    return(list(error = "Need at least 3 zones."))
  }

  mat    <- build_zone_matrix(sel_zones)
  method <- if (tolower(method) %in% c("pearson", "spearman")) tolower(method) else "pearson"

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
    lapply(rownames(m), function(r) setNames(as.list(m[r, ]), colnames(m))) |>
      setNames(rownames(m))
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
#* @param id       4-digit kommune code (e.g. "0101")
#* @param variable One of: income, population, foreign_pct,
#*                 unemployment_rate, crime_rate
zone_timeseries <- function(id = "", variable = "income", res) {
  if (id == "") {
    res$status <- 400
    return(list(error = "Provide a zone id."))
  }

  ts_root <- final_json$timeseries
  if (is.null(ts_root)) {
    res$status <- 503
    return(list(error = "Time series not available in this build of data.json."))
  }

  allowed <- c("income", "population", "foreign_pct", "unemployment_rate", "crime_rate")
  if (!variable %in% allowed) {
    res$status <- 400
    return(list(error = paste("variable must be one of:", paste(allowed, collapse = ", "))))
  }

  series <- ts_root[[variable]]
  if (is.null(series)) {
    res$status <- 404
    return(list(error = paste("No series found for variable:", variable)))
  }

  values <- series[[id]]
  if (is.null(values)) {
    res$status <- 404
    return(list(error = paste("No data for zone:", id, "in variable:", variable)))
  }

  list(
    zone     = id,
    variable = variable,
    years    = unlist(series$years),
    values   = as.numeric(unlist(values))
  )
}
