# ============================================================
# fetch_austria_data.R
#
# Builds final_json for the Austrian Area Profile Builder.
# No API key or registration required — all sources are public.
#
# Primary source:
#   OGDEXT_AEST_GEMTAB_1 — Statistik Austria
#   "Gemeindeergebnisse der Abgestimmten Erwerbsstatistik"
#   Annual data 2011–present at Gemeinde level.
#   URL: https://data.statistik.gv.at/data/OGDEXT_AEST_GEMTAB_1.csv
#
#   Variables available:
#     BEV_ABSOLUT   Total population
#     BEV_UNTER15   % population under 15
#     BEV_UEBER65   % population over 65
#     AUSL_STAATSB  % with foreign citizenship
#     EWTQ_15BIS64  Employment rate (15–64)
#     ALQ_15PLUS    Unemployment rate (15+)
#     EDU_15_SEK    % secondary education
#     EDU_15_TER    % tertiary education
#     AUSPENDLER    % out-commuters
#     PHH           Number of private households
#     HH_SIZE       Average household size
#     FAMILIEN      Number of families
#     BESCH_AST     Employees at local workplaces
#
# Geographic hierarchy derived directly from the GCD code:
#   GCD digit 1       → Bundesland (1=Burgenland … 9=Wien)
#   GCD digits 1–3    → Bezirk
#   GCD digits 1–5    → Gemeinde
#   (no separate lookup file needed)
#
# Optional:
#   ÖROK urban-rural typology — one-time manual download
#   https://www.oerok.gv.at/raum-region/daten-und-grundlagen/regionsabgrenzungen/
#   Save as: create-js/inputs/oerok_typology.csv
#   Columns: GKZ (5-digit), UrbanRuralTyp (1–6)
# ============================================================


# ---- Bundesland lookup (derived from first digit of GCD) ----
bundesland_names <- c(
  "1" = "Burgenland",
  "2" = "Kärnten",
  "3" = "Niederösterreich",
  "4" = "Oberösterreich",
  "5" = "Salzburg",
  "6" = "Steiermark",
  "7" = "Tirol",
  "8" = "Vorarlberg",
  "9" = "Wien"
)

# ---- Variable definitions ----
# Maps the raw CSV column names to human-readable domain groups.
# Each domain group becomes a chart category in the dashboard.
VARIABLE_MAP <- list(

  Altersstruktur = list(
    `Unter 15 Jahre (%)` = "BEV_UNTER15",
    `Über 65 Jahre (%)`  = "BEV_UEBER65"
  ),

  Arbeitsmarkt = list(
    `Beschäftigungsquote (%)` = "EWTQ_15BIS64",
    `Arbeitslosenquote (%)`   = "ALQ_15PLUS",
    `Auspendleranteil (%)`    = "AUSPENDLER"
  ),

  Wirtschaft = list(
    `Beschäftigte`   = "BESCH_AST",
    `Unternehmen`    = "UNT",
    `Arbeitsstätten` = "AST"
  ),

  Bildung = list(
    `Sekundarbildung (%)` = "EDU_15_SEK",
    `Tertiärbildung (%)`  = "EDU_15_TER"
  ),

  Migration = list(
    `Ausländische Staatsbürger (%)` = "AUSL_STAATSB"
  ),

  Haushalte = list(
    `Durchschnittliche Haushaltsgröße` = "HH_SIZE",
    `Privathaushalte`                  = "PHH",
    `Familien`                         = "FAMILIEN"
  )
)

# Indicators used for Bezirk / Austria Total aggregation.
# "pct" = population-weighted mean; "sum" = sum across Gemeinden.
AGGREGATION_TYPE <- list(
  BEV_ABSOLUT  = "sum",
  BEV_UNTER15  = "pct",
  BEV_UEBER65  = "pct",
  AUSL_STAATSB = "pct",
  EWTQ_15BIS64 = "pct",
  ALQ_15PLUS   = "pct",
  EDU_15_SEK   = "pct",
  EDU_15_TER   = "pct",
  AUSPENDLER   = "pct",
  PHH          = "sum",
  HH_SIZE      = "pct",
  FAMILIEN     = "sum",
  BESCH_AST    = "sum",
  UNT          = "sum",
  AST          = "sum"
)

# All numeric indicator columns (excl. metadata)
INDICATOR_COLS <- names(AGGREGATION_TYPE)

# Only columns present in the raw CSV — derived cols are computed later
RAW_COLS <- c("BEV_ABSOLUT","BEV_UNTER15","BEV_UEBER65","AUSL_STAATSB",
              "EWTQ_15BIS64","ALQ_15PLUS","EDU_15_SEK","EDU_15_TER",
              "AUSPENDLER","PHH","HH_SIZE","FAMILIEN","BESCH_AST",
              "UNT","AST")


# ============================================================
# 1. Load the main dataset
# ============================================================
message("Fetching OGDEXT_AEST_GEMTAB_1 from Statistik Austria OGD...")

raw_url <- paste0(OGD_BASE_URL, "/OGDEXT_AEST_GEMTAB_1.csv")

aest_raw <- tryCatch(
  read.csv(raw_url, sep = ";", fileEncoding = "latin1",
           stringsAsFactors = FALSE, check.names = TRUE),
  error = function(e) stop("Could not fetch OGDEXT_AEST_GEMTAB_1: ", conditionMessage(e))
)

# Clean: fix decimal commas, coerce to numeric
aest <- aest_raw |>
  as_tibble() |>
  mutate(
    GCD  = sprintf("%05d", as.integer(GCD)),
    JAHR = as.integer(JAHR)
  ) |>
  mutate(across(all_of(RAW_COLS), ~ as.numeric(gsub(",", ".", .x))))

latest_year <- max(aest$JAHR, na.rm = TRUE)
message(sprintf("  %d Gemeinden | years %d–%d | using %d",
                n_distinct(aest$GCD), min(aest$JAHR), latest_year, latest_year))

# Snapshot: most recent year only (used for profile builder)
aest_now <- filter(aest, JAHR == latest_year)

# Derive administrative hierarchy from GCD
aest_now <- aest_now |>
  mutate(
    bezirk_code = substr(GCD, 1, 3),
    bundesland  = bundesland_names[substr(GCD, 1, 1)]
  )



# ============================================================
# 1b. Eurostat NUTS3 data — GDP per capita
# Free, no API key. NUTS3 (~35 regions) mapped to Bezirke via
# the Eurostat LAU correspondence file, with NUTS2 fallback.
# ============================================================
message("Fetching Eurostat NUTS3 data...")

# Helper: pick most recent row per group (avoids base::time() name clash)
latest_per_group <- function(df, ...) {
  grp_vars <- rlang::enquos(...)
  time_col  <- intersect(c("TIME_PERIOD", "time"), names(df))[1]
  if (is.na(time_col)) stop("No time/TIME_PERIOD column found")
  df |>
    arrange(desc(.data[[time_col]])) |>
    distinct(!!!grp_vars, .keep_all = TRUE)
}

# Helper: collapse NUTS3 (5-char) data to NUTS2 (4-char) by simple mean
# Used when LAU mapping fails and we fall back to Bundesland-level codes
collapse_to_nuts2 <- function(df) {
  df |>
    mutate(nuts3_code = substr(nuts3_code, 1, 4)) |>
    group_by(nuts3_code) |>
    summarise(across(where(is.numeric), ~ mean(.x, na.rm = TRUE)),
              .groups = "drop")
}

# Build Bezirk → NUTS code lookup (NUTS3 preferred, NUTS2 fallback)
nuts_level      <- 5L   # will be set to 4 if falling back to NUTS2
bezirk_to_nuts3 <- tryCatch({
  message("  Downloading Eurostat LAU-NUTS3 correspondence...")
  tmp <- tempfile(fileext = ".xlsx")

  lau_urls <- c(
    "https://ec.europa.eu/eurostat/documents/345175/501971/EU-27-LAU-2023-NUTS-2021.xlsx",
    "https://ec.europa.eu/eurostat/documents/345175/501971/EU-27-LAU-2022-NUTS-2021.xlsx"
  )

  lau_df <- NULL
  for (url in lau_urls) {
    result <- tryCatch({
      httr::GET(url, httr::write_disk(tmp, overwrite = TRUE), httr::timeout(60))
      readxl::read_excel(tmp, sheet = 1)
    }, error = function(e) NULL)
    if (!is.null(result) && nrow(result) > 0) { lau_df <- result; break }
  }
  if (is.null(lau_df)) stop("LAU file unavailable")

  clean_df <- janitor::clean_names(lau_df)
  message(sprintf("  LAU file columns: %s", paste(names(clean_df), collapse = ", ")))

  nuts3_col <- grep("nuts.*3|nuts3", names(clean_df), value = TRUE, ignore.case = TRUE)[1]
  lau_col   <- grep("^lau", names(clean_df), value = TRUE, ignore.case = TRUE)[1]
  if (is.na(nuts3_col) || is.na(lau_col))
    stop(sprintf("Columns not found. Available: %s", paste(names(clean_df), collapse = ", ")))

  lau_at <- clean_df |>
    filter(grepl("^AT", .data[[nuts3_col]])) |>
    mutate(
      gkz         = sprintf("%05d",
                    as.integer(gsub("[^0-9]", "", as.character(.data[[lau_col]])))),
      bezirk_code = substr(gkz, 1, 3)
    ) |>
    distinct(bezirk_code, .keep_all = TRUE) |>
    select(bezirk_code, nuts3_code = !!nuts3_col)

  message(sprintf("  LAU mapping: %d Bezirke → NUTS3", nrow(lau_at)))
  setNames(lau_at$nuts3_code, lau_at$bezirk_code)

}, error = function(e) {
  message(sprintf("  LAU fetch failed (%s) — using NUTS2 fallback", conditionMessage(e)))
  nuts_level <<- 4L
  bl_nuts2 <- c("1"="AT11","2"="AT21","3"="AT12","4"="AT31",
                 "5"="AT32","6"="AT22","7"="AT33","8"="AT34","9"="AT13")
  bzk <- unique(aest_now$bezirk_code)
  setNames(bl_nuts2[substr(bzk, 1, 1)], bzk)
})

aest_now <- aest_now |>
  mutate(nuts3_code = bezirk_to_nuts3[bezirk_code])

# Population density via NUTS3 area (reg_area3)
# Used only for map density_class segmentation — not shown as a chart indicator.
area_nuts3 <- tryCatch({
  message("  Fetching NUTS3 area (reg_area3)...")
  land_col <- NULL
  raw <- eurostat::get_eurostat("reg_area3", time_format = "num")
  land_col <- grep("^land", names(raw), value = TRUE, ignore.case = TRUE)[1]
  df <- raw |>
    filter(grepl("^AT[0-9]{3}$", geo), .data[[land_col]] == "TOTAL") |>
    latest_per_group(geo) |>
    select(nuts3_code = geo, area_km2 = values)
  if (nuts_level == 4L) df <- collapse_to_nuts2(df)
  message(sprintf("  Area: %d regions", nrow(df)))
  df
}, error = function(e) { message("  reg_area3 failed: ", conditionMessage(e)); NULL })

if (!is.null(area_nuts3) && nrow(area_nuts3) > 0) {
  nuts3_pop  <- aest_now |>
    group_by(nuts3_code) |>
    summarise(nuts3_bev = sum(BEV_ABSOLUT, na.rm = TRUE), .groups = "drop")
  density_df <- nuts3_pop |>
    left_join(area_nuts3, by = "nuts3_code") |>
    mutate(BEV_DICHTE = if_else(area_km2 > 0,
                                round(nuts3_bev / area_km2, 1), NA_real_)) |>
    select(nuts3_code, BEV_DICHTE)
  aest_now <- aest_now |> left_join(density_df, by = "nuts3_code")
} else {
  aest_now$BEV_DICHTE <- NA_real_
}


# ============================================================
# 2. Urban-rural classification
# ============================================================
# Priority order:
#   1. ÖROK CSV if present at create-js/inputs/oerok_typology.csv
#   2. Derived from population size (Eurostat DEGURBA-aligned thresholds)
#
# Derived thresholds (Eurostat DEGURBA LAU methodology, adapted):
#   Städtisch   >= 20 000 inhabitants  (cities)
#   Intermediär  5 000 – 19 999        (towns & suburbs)
#   Ländlich    <  5 000               (rural areas)
#
# These thresholds are transparent and reproducible. Replace with
# official DEGURBA data when available via Eurostat LAU Excel tables
# at: https://ec.europa.eu/eurostat/web/nuts/local-administrative-units
# ============================================================

classify_urban_rural <- function(bev) {
  dplyr::case_when(
    bev >= 20000 ~ "Städtisch",
    bev >=  5000 ~ "Intermediär",
    TRUE         ~ "Ländlich"
  )
}

oerok_path <- paste0(data_source_root, "oerok_typology.csv")

if (file.exists(oerok_path)) {
  message("Loading ÖROK urban-rural typology from file...")
  oerok_df <- read.csv(oerok_path, stringsAsFactors = FALSE) |>
    as_tibble() |>
    janitor::clean_names() |>
    mutate(
      GCD = sprintf("%05d", as.integer(gkz)),
      urban_rural_status = dplyr::case_when(
        urban_rural_typ %in% 1:2 ~ "Städtisch",
        urban_rural_typ %in% 3:4 ~ "Intermediär",
        urban_rural_typ %in% 5:6 ~ "Ländlich",
        TRUE                     ~ NA_character_
      )
    ) |>
    select(GCD, urban_rural_status)
  message(sprintf("  %d Gemeinden classified from ÖROK file", nrow(oerok_df)))
  aest_now <- left_join(aest_now, oerok_df, by = "GCD")

} else {
  message(paste(
    "No ÖROK typology file found — deriving urban-rural status from",
    "population size (DEGURBA-aligned thresholds: >=20k Städtisch,",
    "5k-20k Intermediär, <5k Ländlich)."
  ))
  aest_now <- aest_now |>
    mutate(urban_rural_status = classify_urban_rural(BEV_ABSOLUT))
}

# Summary
ur_counts <- table(aest_now$urban_rural_status)
message(sprintf("  Urban-rural breakdown: %s",
  paste(names(ur_counts), ur_counts, sep = "=", collapse = " | ")))


# ============================================================
# 2b. Additional segmentation axes
# ============================================================

# Settlement size — based on population absolute count
classify_settlement <- function(bev) {
  dplyr::case_when(
    bev >= 50000 ~ "Großstadt",
    bev >= 10000 ~ "Kleinstadt",
    bev >=  2000 ~ "Marktgemeinde",
    TRUE         ~ "Dorfgemeinde"
  )
}

# Population density — based on BEV_DICHTE (inh/km²)
classify_density <- function(dens) {
  dplyr::case_when(
    is.na(dens)   ~ "Unbekannt",
    dens >= 1000  ~ "Sehr dicht",
    dens >=  300  ~ "Dicht",
    dens >=  100  ~ "Mittel",
    TRUE          ~ "Dünn"
  )
}

aest_now <- aest_now |>
  mutate(
    settlement_class = classify_settlement(BEV_ABSOLUT),
    density_class    = classify_density(BEV_DICHTE)
  )

message(sprintf("  Settlement classes: %s",
  paste(names(table(aest_now$settlement_class)), table(aest_now$settlement_class), sep="=", collapse=" | ")))
message(sprintf("  Density classes: %s",
  paste(names(table(aest_now$density_class)), table(aest_now$density_class), sep="=", collapse=" | ")))


# ============================================================
# Helper: build domain-grouped indicator list for one row
# ============================================================
build_indicator_list <- function(row_data) {
  lapply(VARIABLE_MAP, function(domain) {
    lapply(names(domain), function(label) {
      col <- domain[[label]]
      val <- row_data[[col]]
      if (is.null(val) || length(val) == 0 || is.na(val)) return(NULL)
      as.numeric(val)
    }) |> setNames(names(domain))
  })
}


# ============================================================
# 3. Build Gemeinde entries
# ============================================================
message("Building Gemeinde entries...")

gemeinde_entries <- lapply(seq_len(nrow(aest_now)), function(i) {
  row <- aest_now[i, ]
  indicators <- build_indicator_list(row)
  ur <- if (!is.na(row$urban_rural_status)) row$urban_rural_status else NA

  c(
    list(
      Urban_rural_status = ur,
      Settlement_class   = row$settlement_class,
      Density_class      = row$density_class,
      Bezirk             = row$bezirk_code,
      Gemeindename       = row$GEM_NAME,
      Bundesland         = row$bundesland,
      Bevölkerung        = as.integer(row$BEV_ABSOLUT)
    ),
    indicators
  )
}) |> setNames(aest_now$GCD)


# ============================================================
# 4. Build Bezirk entries (population-weighted aggregation)
# ============================================================
message("Building Bezirk entries...")

build_bezirk_entry <- function(bzk_code, gem_rows) {
  total_pop <- sum(gem_rows$BEV_ABSOLUT, na.rm = TRUE)

  # Build a synthetic "row" with aggregated values
  agg_row <- list(GCD = bzk_code, GEM_NAME = bzk_code,
                  bezirk_code = bzk_code,
                  bundesland = gem_rows$bundesland[1])

  for (col in INDICATOR_COLS) {
    vals <- gem_rows[[col]]
    pops <- gem_rows$BEV_ABSOLUT
    ok   <- !is.na(vals) & !is.na(pops) & pops > 0

    if (!any(ok)) {
      agg_row[[col]] <- NA_real_
    } else if (AGGREGATION_TYPE[[col]] == "sum") {
      agg_row[[col]] <- sum(vals[ok], na.rm = TRUE)
    } else {
      agg_row[[col]] <- sum(vals[ok] * pops[ok]) / sum(pops[ok])
    }
  }
  agg_row <- as_tibble(agg_row)

  # Majority class helper
  majority_class <- function(col) {
    t <- table(col)
    if (length(t) == 0) return(NA_character_)
    names(sort(t, decreasing = TRUE))[1]
  }

  majority_ur         <- majority_class(gem_rows$urban_rural_status)
  majority_settlement <- majority_class(gem_rows$settlement_class)
  majority_density    <- majority_class(gem_rows$density_class)

  indicators <- build_indicator_list(agg_row)

  c(
    list(
      Urban_rural_status = majority_ur,
      Settlement_class   = majority_settlement,
      Density_class      = majority_density,
      Bundesland         = gem_rows$bundesland[1],
      Bevölkerung        = as.integer(sum(gem_rows$BEV_ABSOLUT, na.rm = TRUE))
    ),
    indicators
  )
}

bezirk_codes   <- unique(aest_now$bezirk_code)
bezirk_entries <- lapply(bezirk_codes, function(bzk) {
  rows <- filter(aest_now, bezirk_code == bzk)
  build_bezirk_entry(bzk, rows)
}) |> setNames(bezirk_codes)


# ============================================================
# 5. Build Austria Total (population-weighted national means)
# ============================================================
message("Building Austria Total...")

total_pop <- sum(aest_now$BEV_ABSOLUT, na.rm = TRUE)

austria_total_row <- list()
for (col in INDICATOR_COLS) {
  vals <- aest_now[[col]]
  pops <- aest_now$BEV_ABSOLUT
  ok   <- !is.na(vals) & !is.na(pops) & pops > 0

  if (!any(ok)) {
    austria_total_row[[col]] <- NA_real_
  } else if (AGGREGATION_TYPE[[col]] == "sum") {
    austria_total_row[[col]] <- sum(vals[ok])
  } else {
    austria_total_row[[col]] <- round(sum(vals[ok] * pops[ok]) / sum(pops[ok]), 1)
  }
}
austria_total_row <- as_tibble(austria_total_row)
austria_total     <- build_indicator_list(austria_total_row)


# ============================================================
# 6. Assemble final_json
# ============================================================
final_json <- list(
  "Austria Total" = austria_total,
  "Bezirk"        = lapply(bezirk_entries, convert_to_named_list),
  "Gemeinde"      = lapply(gemeinde_entries, convert_to_named_list)
)

message(sprintf(
  "Done. Austria Total + %d Bezirke + %d Gemeinden ready.",
  length(bezirk_entries), length(gemeinde_entries)
))
