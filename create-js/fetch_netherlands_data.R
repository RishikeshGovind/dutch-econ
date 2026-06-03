# ============================================================
# fetch_netherlands_data.R
#
# Builds final_json for the Dutch Municipality Profile Builder.
# No API key required — all sources are public.
#
# Sources:
#   PDOK/CBS WFS      (service.pdok.nl)         — gemeente/provincie geography
#   CBS OData API     (opendata.cbs.nl)          — statistics
#   CBS Energy        (opendata.cbs.nl)          — renewable energy by municipality
#   KNMI              (climexp.knmi.nl)          — climate baseline
#   ENTSO-E           (web-api.tp.entsoe.eu)     — NL electricity load & prices
#                     set ENTSOE_API_KEY env var for live fetch (free registration)
#
# Geographic hierarchy:
#   Provincie (12) ← Gemeente (342)
#
# CBS notes:
#   - Municipality codes (RegioS) use "GM" prefix + 4-digit zero-padded code
#   - We normalise to 4-digit in data.json (e.g. "0363" for Amsterdam)
#   - Period format: annual = "2023JJ00", quarterly = "2023KW01"
# ============================================================

library(dplyr)
library(tidyr)
library(tibble)
library(readr)
library(httr)
library(jsonlite)
library(janitor)
library(here)

CBS_BASE   <- "https://opendata.cbs.nl/ODataApi/odata/"
PDOK_BASE  <- "https://service.pdok.nl/"
KNMI_BASE  <- "https://climexp.knmi.nl/"

# ---- Domain → indicator → internal column mapping ----
VARIABLE_MAP <- list(
  AgeStructure = list(
    `Under 15 years (%)` = "BEV_UNDER15",
    `Over 65 years (%)`  = "BEV_OVER65"
  ),
  LabourMarket = list(
    `Employment rate (%)`   = "EMP_RATE",
    `Unemployment rate (%)` = "UNEMP_RATE"
  ),
  Economy = list(
    `Employees`           = "EMPLOYEES",
    `Avg income (€/year)` = "AVG_INCOME"
  ),
  Education = list(
    `Higher education (%)` = "EDU_HIGHER"
  ),
  Migration = list(
    `Non-Dutch citizens (%)` = "FOREIGN_PCT"
  ),
  Housing = list(
    `Owner-occupied (%)` = "OWNER_PCT",
    `Social housing (%)`  = "SOCIAL_PCT",
    `Dwellings`           = "DWELLINGS"
  ),
  Safety = list(
    `Crimes per 1,000` = "CRIMES_PER_1K"
  ),
  PopulationDynamics = list(
    `Birth rate (per 1,000)`    = "BIRTH_RATE",
    `Death rate (per 1,000)`    = "DEATH_RATE",
    `Net migration (per 1,000)` = "NET_MIGRATION",
    `Population growth (%)`     = "POP_GROWTH"
  ),
  Businesses = list(
    `Establishments`           = "BUSINESSES",
    `Establishments per 1,000` = "BUSINESSES_PER_1K"
  ),
  IndustrySectors = list(
    `Agriculture, forestry & fishing (%)` = "SECTOR_AGR_PCT",
    `Manufacturing & utilities (%)`        = "SECTOR_MANUF_PCT",
    `Construction (%)`                     = "SECTOR_CONSTRUCT_PCT",
    `Trade & transport (%)`                = "SECTOR_TRADE_PCT",
    `ICT (%)`                              = "SECTOR_ICT_PCT",
    `Finance & insurance (%)`             = "SECTOR_FINANCE_PCT",
    `Public admin, edu & health (%)`      = "SECTOR_PUBLIC_PCT"
  ),
  GreenEnergy = list(
    `Solar capacity (MW)`           = "SOLAR_MW",
    `Wind capacity (MW)`            = "WIND_MW",
    `Total renewable capacity (MW)` = "TOTAL_RENEWABLE_MW",
    `Renewable per 1,000 people`    = "RENEWABLE_MW_PER_1K"
  ),
  EnergyDemand = list(
    `Gas consumption (m³/connection)`         = "GAS_M3_PC",
    `Electricity consumption (kWh/connection)` = "ELEC_KWH_PC"
  )
)

AGGREGATION_TYPE <- list(
  POPULATION          = "sum",
  BEV_UNDER15         = "pct",
  BEV_OVER65          = "pct",
  EMP_RATE            = "pct",
  UNEMP_RATE          = "pct",
  EMPLOYEES           = "sum",
  AVG_INCOME          = "pct",
  EDU_HIGHER          = "pct",
  FOREIGN_PCT         = "pct",
  OWNER_PCT           = "pct",
  SOCIAL_PCT          = "pct",
  DWELLINGS           = "sum",
  CRIMES_PER_1K       = "pct",
  BIRTH_RATE          = "pct",
  DEATH_RATE          = "pct",
  NET_MIGRATION       = "pct",
  POP_GROWTH          = "pct",
  BUSINESSES          = "sum",
  BUSINESSES_PER_1K   = "pct",
  SECTOR_AGR_PCT      = "pct",
  SECTOR_MANUF_PCT    = "pct",
  SECTOR_CONSTRUCT_PCT = "pct",
  SECTOR_TRADE_PCT    = "pct",
  SECTOR_ICT_PCT      = "pct",
  SECTOR_FINANCE_PCT  = "pct",
  SECTOR_PUBLIC_PCT   = "pct",
  SOLAR_MW            = "sum",
  WIND_MW             = "sum",
  TOTAL_RENEWABLE_MW  = "sum",
  RENEWABLE_MW_PER_1K = "pct",
  GAS_M3_PC           = "pct",
  ELEC_KWH_PC         = "pct"
)
INDICATOR_COLS <- names(AGGREGATION_TYPE)

# ============================================================
# Helpers
# ============================================================

# Fetch CBS OData TypedDataSet; returns tibble or NULL on failure
cbs_get <- function(table, filter = "", top = 50000) {
  url <- paste0(CBS_BASE, table, "/TypedDataSet?$top=", top)
  if (nchar(filter) > 0)
    url <- paste0(url, "&$filter=", utils::URLencode(filter, reserved = TRUE))
  resp <- tryCatch(
    httr::GET(url, httr::accept_json(), httr::timeout(120)),
    error = function(e) { message("  GET failed (", table, "): ", conditionMessage(e)); NULL }
  )
  if (is.null(resp) || httr::http_error(resp)) {
    if (!is.null(resp))
      message(sprintf("  %s HTTP %s", table, httr::status_code(resp)))
    return(NULL)
  }
  raw <- tryCatch(
    jsonlite::fromJSON(httr::content(resp, "text", encoding = "UTF-8"))$value,
    error = function(e) { message("  Parse failed (", table, "): ", conditionMessage(e)); NULL }
  )
  if (is.null(raw) || length(raw) == 0) return(NULL)
  as_tibble(raw)
}

# Find the latest annual period in a CBS table (format "YYYYjj00")
cbs_latest_year <- function(table) {
  url <- paste0(CBS_BASE, table, "/Perioden?$top=200&$orderby=Key desc")
  resp <- tryCatch(httr::GET(url, httr::accept_json(), httr::timeout(30)), error = function(e) NULL)
  if (is.null(resp) || httr::http_error(resp)) return(NULL)
  vals <- tryCatch(
    jsonlite::fromJSON(httr::content(resp, "text", encoding = "UTF-8"))$value$Key,
    error = function(e) NULL
  )
  if (is.null(vals)) return(NULL)
  annual <- grep("JJ00$", vals, value = TRUE)
  if (length(annual) == 0) return(NULL)
  tail(sort(annual), 1)
}

# 4-digit zero-padded gemeente code from CBS RegioS (e.g. "GM0363  " → "0363")
extract_gem_code <- function(x) {
  num <- suppressWarnings(as.integer(sub("^GM0*", "", trimws(x))))
  sprintf("%04d", num)
}

# CBS RegioS format from 4-digit code (e.g. "0363" → "GM0363  " trimmed to "GM0363")
to_regio_s <- function(x) sprintf("GM%04d", suppressWarnings(as.integer(x)))

# Find numeric value column(s) in a CBS tibble (pattern-match by name)
find_val_col <- function(df, patterns) {
  for (p in patterns) {
    hits <- grep(p, names(df), value = TRUE, ignore.case = TRUE)
    if (length(hits) > 0) return(hits[1])
  }
  NULL
}

build_indicator_list <- function(row_data) {
  lapply(VARIABLE_MAP, function(domain) {
    lapply(names(domain), function(label) {
      col <- domain[[label]]
      val <- row_data[[col]]
      if (is.null(val) || length(val) == 0 || is.na(val)) return(NULL)
      round(as.numeric(val), 2)
    }) |> setNames(names(domain))
  })
}

convert_to_named_list <- function(x) {
  lapply(x, function(category) {
    if (is.list(category)) category else unname(category)
  })
}

TS_YEARS <- as.character(2012:2023)

ts_make <- function(wide, dk_row, period_ids, year_labels) {
  dk_vals <- if (is.data.frame(dk_row))
    as.list(unname(as.numeric(dk_row[1, period_ids])))
  else
    as.list(unname(as.numeric(dk_row[period_ids])))
  c(
    list(years = as.list(year_labels)),
    list("000" = dk_vals),
    setNames(
      lapply(seq_len(nrow(wide)), function(i)
        as.list(unname(as.numeric(wide[i, period_ids])))),
      wide$gemeente_kode
    )
  )
}


# ============================================================
# 1. Geography from PDOK (CBS administrative boundaries)
# ============================================================
message("Fetching gemeente geography from PDOK/CBS...")

gem_wfs_url <- paste0(
  PDOK_BASE,
  "cbs/gebiedsindelingen/2024/wfs/v1_0",
  "?service=WFS&version=2.0.0&request=GetFeature",
  "&typeName=gebiedsindelingen:gemeente_gegeneraliseerd",
  "&outputFormat=application/json&count=1000"
)

gem_raw <- tryCatch({
  resp <- httr::GET(gem_wfs_url, httr::timeout(60))
  if (httr::http_error(resp)) stop("HTTP error")
  jsonlite::fromJSON(httr::content(resp, "text", encoding = "UTF-8"),
                     simplifyDataFrame = TRUE)
}, error = function(e) {
  message("  PDOK WFS failed: ", conditionMessage(e)); NULL
})

gemeente_df <- NULL
if (!is.null(gem_raw) && !is.null(gem_raw$features)) {
  props <- gem_raw$features$properties
  gemeente_df <- as_tibble(as.data.frame(props)) |>
    mutate(
      gemeente_kode = sprintf("%04d",
        suppressWarnings(as.integer(sub("^GM0*", "", trimws(statcode))))),
      gemeente_naam = as.character(statnaam)
    )
  # Try to extract province name from WFS fields
  pv_col <- grep("pv_naam|prov|province", names(gemeente_df), value = TRUE, ignore.case = TRUE)
  if (length(pv_col) > 0) {
    gemeente_df$provincie_naam <- as.character(gemeente_df[[pv_col[1]]])
  } else {
    # Fallback: fetch province layer separately and spatial join by name
    message("  Province field not in WFS; fetching provincie layer...")
    prov_url <- paste0(
      PDOK_BASE,
      "cbs/gebiedsindelingen/2024/wfs/v1_0",
      "?service=WFS&version=2.0.0&request=GetFeature",
      "&typeName=gebiedsindelingen:provincie_gegeneraliseerd",
      "&outputFormat=application/json&count=20"
    )
    prov_raw <- tryCatch({
      pr <- httr::GET(prov_url, httr::timeout(30))
      if (httr::http_error(pr)) NULL
      else jsonlite::fromJSON(httr::content(pr, "text", encoding = "UTF-8"), simplifyDataFrame = TRUE)
    }, error = function(e) NULL)

    if (!is.null(prov_raw) && !is.null(prov_raw$features)) {
      prov_props <- prov_raw$features$properties
      gemeente_df$provincie_naam <- NA_character_
      # Match via rubriek or statnaam if available
    } else {
      gemeente_df$provincie_naam <- NA_character_
    }
  }
  message(sprintf("  %d gemeenten loaded from PDOK", nrow(gemeente_df)))
} else {
  message("  PDOK WFS returned no data — using CBS fallback list")
}

# Fallback: If PDOK failed, build gemeente list from CBS population table
if (is.null(gemeente_df) || nrow(gemeente_df) == 0) {
  latest_pop_period <- cbs_latest_year("03759NED")
  if (!is.null(latest_pop_period)) {
    gem_list <- cbs_get("03759NED",
      filter = paste0("startswith(RegioS,'GM') and Perioden eq '", latest_pop_period, "' and Geslacht eq 'T001038' and Leeftijd eq 'LTOT'"),
      top = 1000)
    if (!is.null(gem_list)) {
      gemeente_df <- gem_list |>
        mutate(
          gemeente_kode = extract_gem_code(RegioS),
          gemeente_naam = trimws(RegioS),   # Names come from a separate lookup; use code for now
          provincie_naam = NA_character_
        ) |>
        select(gemeente_kode, gemeente_naam, provincie_naam) |>
        distinct()
    }
  }
}

# Fallback: static province-from-code lookup using CBS known ranges
PROV_LOOKUP <- tibble::tribble(
  ~min_code, ~max_code, ~provincie_naam,
  3,    18,   "Groningen",
  50,   90,   "Friesland",
  100,  120,  "Drenthe",
  147,  200,  "Overijssel",
  230,  243,  "Flevoland",
  193,  230,  "Overijssel",    # overlap; refine if needed
  244,  400,  "Gelderland",
  272,  313,  "Utrecht",
  307,  400,  "Noord-Holland",
  361,  399,  "Utrecht",
  400,  600,  "Noord-Holland",
  394,  600,  "Zuid-Holland",
  501,  600,  "Zuid-Holland",
  600,  700,  "Zeeland",
  664,  800,  "Noord-Brabant",
  700,  899,  "Noord-Brabant",
  880,  1000, "Limburg"
)

# Simpler: use the known 2024 municipality count as a sanity check
if (!is.null(gemeente_df) && !"provincie_naam" %in% names(gemeente_df)) {
  gemeente_df$provincie_naam <- NA_character_
}

# Hardcode province codes from CBS for accurate mapping
# Full mapping derived from CBS 2024 municipal register
PROV_RANGES <- list(
  "Groningen"    = c(3, 18),
  "Friesland"    = c(50, 90),
  "Drenthe"      = c(100, 120),
  "Overijssel"   = c(147, 200),
  "Flevoland"    = c(166, 243),
  "Gelderland"   = c(193, 340),
  "Utrecht"      = c(307, 399),
  "Noord-Holland" = c(358, 490),
  "Zuid-Holland"  = c(484, 692),
  "Zeeland"      = c(664, 718),
  "Noord-Brabant" = c(703, 878),
  "Limburg"      = c(882, 1000)
)

lookup_provincie <- function(code_int) {
  # CBS municipality codes are not strictly ordered by province.
  # Use the StatLine lookup when possible; fall back to a best-guess range.
  best <- NA_character_
  best_width <- Inf
  for (pv in names(PROV_RANGES)) {
    rng <- PROV_RANGES[[pv]]
    if (code_int >= rng[1] && code_int <= rng[2]) {
      width <- rng[2] - rng[1]
      if (width < best_width) { best <- pv; best_width <- width }
    }
  }
  best
}

# Try to pull the exact gemeente→provincie mapping from CBS StatLine
message("Fetching gemeente–provincie mapping from CBS...")
prov_map_raw <- cbs_get("70072NED",
  filter = "startswith(RegioS,'GM')",
  top = 1000)

if (!is.null(prov_map_raw) && "Codering_3" %in% names(prov_map_raw)) {
  # 70072NED has Codering_3 = province code
  prov_map_df <- prov_map_raw |>
    select(RegioS, any_of(c("Naam_2","Title","Codering_3","Provincienaam"))) |>
    distinct() |>
    mutate(gemeente_kode = extract_gem_code(RegioS))
} else {
  # Better source: RegioIndelingen table
  prov_map_raw2 <- cbs_get("84583NED",
    filter = "startswith(GemeentecodeGM,'GM')",
    top = 2000)
  if (!is.null(prov_map_raw2)) {
    prov_map_df <- prov_map_raw2
  } else {
    prov_map_df <- NULL
  }
}

# Merge province onto gemeente_df
if (!is.null(gemeente_df)) {
  if (!is.null(prov_map_df) && "provincie_naam" %in% names(prov_map_df)) {
    gemeente_df <- gemeente_df |>
      left_join(prov_map_df |> select(gemeente_kode, provincie_naam) |> distinct(),
                by = "gemeente_kode", suffix = c("", ".new")) |>
      mutate(provincie_naam = coalesce(provincie_naam, provincie_naam.new)) |>
      select(-any_of("provincie_naam.new"))
  }
  # Fill remaining NAs with range-based lookup
  if (any(is.na(gemeente_df$provincie_naam))) {
    gemeente_df <- gemeente_df |>
      mutate(provincie_naam = if_else(
        is.na(provincie_naam),
        sapply(suppressWarnings(as.integer(gemeente_kode)), lookup_provincie),
        provincie_naam
      ))
  }
}

if (is.null(gemeente_df) || nrow(gemeente_df) == 0)
  stop("Could not load gemeente geography from any source.")

gemeente_lookup <- gemeente_df |>
  select(gemeente_kode, gemeente_naam, provincie_naam) |>
  distinct() |>
  filter(!is.na(gemeente_kode), !duplicated(gemeente_kode))

provincie_lookup <- gemeente_lookup |>
  select(provincie_naam) |>
  distinct() |>
  filter(!is.na(provincie_naam)) |>
  mutate(provincie_kode = sprintf("PV%02d", row_number()))

gemeente_lookup <- gemeente_lookup |>
  left_join(provincie_lookup, by = "provincie_naam")

message(sprintf("  %d gemeenten across %d provincies",
  nrow(gemeente_lookup), n_distinct(gemeente_lookup$provincie_naam)))


# ============================================================
# 2. CBS 03759NED — Population + age structure
# ============================================================
message("Fetching 03759NED (population + age) from CBS...")

latest_pop <- cbs_latest_year("03759NED")
if (is.null(latest_pop)) latest_pop <- "2023JJ00"

pop_age_df <- tryCatch({
  # Fetch total population and age group breakdown per municipality
  raw <- cbs_get("03759NED",
    filter = paste0(
      "startswith(RegioS,'GM') and Perioden eq '", latest_pop, "' and Geslacht eq 'T001038'"
    ))
  if (is.null(raw)) stop("null response")

  age_col <- find_val_col(raw, c("Leeftijd", "leeftijd"))
  val_col  <- find_val_col(raw, c("BevolkingOpDeEerste", "Bevolking", "Inwoners", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value))

  # Age codes: LTOT = total, Y0T14 = under 15, Y65T99 or Y65TO = 65+
  totals <- df |>
    filter(grepl("LTOT|^TOT|totaal", .data[[age_col]], ignore.case = TRUE)) |>
    group_by(gemeente_kode) |>
    summarise(POPULATION = sum(value, na.rm = TRUE), .groups = "drop")

  u15 <- df |>
    filter(grepl("Y0T14|0.*14|<15|under.*15|onder.*15", .data[[age_col]], ignore.case = TRUE) |
           (suppressWarnings(as.integer(gsub("[^0-9]", "", .data[[age_col]]))) %in% 0:14)) |>
    group_by(gemeente_kode) |>
    summarise(n_under15 = sum(value, na.rm = TRUE), .groups = "drop")

  o65 <- df |>
    filter(grepl("Y65T|65.*jaar|65 jaar|65 tot|65\\+", .data[[age_col]], ignore.case = TRUE) |
           (suppressWarnings(as.integer(gsub("[^0-9]", "", .data[[age_col]]))) >= 65)) |>
    group_by(gemeente_kode) |>
    summarise(n_over65 = sum(value, na.rm = TRUE), .groups = "drop")

  result <- totals |>
    left_join(u15, by = "gemeente_kode") |>
    left_join(o65, by = "gemeente_kode") |>
    mutate(
      BEV_UNDER15 = if_else(POPULATION > 0,
        round(coalesce(n_under15, 0) / POPULATION * 100, 1), NA_real_),
      BEV_OVER65  = if_else(POPULATION > 0,
        round(coalesce(n_over65, 0)  / POPULATION * 100, 1), NA_real_)
    ) |>
    select(gemeente_kode, POPULATION, BEV_UNDER15, BEV_OVER65)

  message(sprintf("  Population: %d gemeenten (period: %s)", nrow(result), latest_pop))
  result
}, error = function(e) { message("  03759NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 3. CBS 03743NED — Non-Dutch citizens
# ============================================================
message("Fetching 03743NED (citizenship) from CBS...")

foreign_df <- tryCatch({
  raw <- cbs_get("03743NED",
    filter = paste0("startswith(RegioS,'GM') and Perioden eq '", latest_pop, "'"))
  if (is.null(raw)) stop("null")

  val_col <- find_val_col(raw, c("Bevolking", "Inwoners", "Antal", "Count"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]
  nat_col <- find_val_col(raw, c("Nationaliteit", "nationality", "Burger"))

  if (is.null(nat_col)) stop("no nationality column")
  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value))

  totals  <- df |> filter(grepl("TOTAAL|TOT|total|totaal", .data[[nat_col]], ignore.case = TRUE)) |>
    group_by(gemeente_kode) |> summarise(total = sum(value, na.rm = TRUE), .groups = "drop")
  dutch   <- df |> filter(grepl("Nederland|Dutch|NL", .data[[nat_col]], ignore.case = TRUE)) |>
    group_by(gemeente_kode) |> summarise(dutch = sum(value, na.rm = TRUE), .groups = "drop")

  result <- totals |> left_join(dutch, by = "gemeente_kode") |>
    mutate(FOREIGN_PCT = if_else(total > 0,
      round((total - coalesce(dutch, 0)) / total * 100, 1), NA_real_)) |>
    select(gemeente_kode, FOREIGN_PCT)
  message(sprintf("  Foreign citizens: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  03743NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 4. CBS 85663NED — Unemployment (WW-uitkeringen per gemeente)
# ============================================================
message("Fetching 85663NED (unemployment) from CBS...")

unemp_df <- tryCatch({
  raw <- cbs_get("85663NED",
    filter = "startswith(RegioS,'GM')",
    top = 10000)
  if (is.null(raw)) stop("null")

  # Get most recent period
  period_col <- find_val_col(raw, c("Perioden", "Period"))
  if (!is.null(period_col)) {
    latest_q <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_q)
  }

  val_col <- find_val_col(raw, c("WerkloosheidsUitkering", "UitvoeringWW", "AantalUitkering", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  unemp_raw <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value)) |>
    group_by(gemeente_kode) |>
    summarise(unemp_count = sum(value, na.rm = TRUE), .groups = "drop")

  result <- unemp_raw |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(gemeente_kode, POPULATION)
              else tibble(gemeente_kode = character(), POPULATION = integer()),
              by = "gemeente_kode") |>
    mutate(UNEMP_RATE = if_else(coalesce(POPULATION, 0L) > 0,
      round(unemp_count / POPULATION * 100, 1), NA_real_)) |>
    select(gemeente_kode, UNEMP_RATE)
  message(sprintf("  Unemployment: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  85663NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 5. CBS 85174NED — Employment (banen per gemeente)
# ============================================================
message("Fetching 85174NED (employment) from CBS...")

emp_df <- tryCatch({
  raw <- cbs_get("85174NED",
    filter = "startswith(RegioS,'GM')",
    top = 10000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden", "Period"))
  if (!is.null(period_col)) {
    latest_p <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }
  val_col <- find_val_col(raw, c("Banen", "Werkzame", "Werknemers", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  result <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value)) |>
    group_by(gemeente_kode) |>
    summarise(EMPLOYEES = as.integer(sum(value, na.rm = TRUE)), .groups = "drop") |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(gemeente_kode, POPULATION)
              else tibble(gemeente_kode = character(), POPULATION = integer()),
              by = "gemeente_kode") |>
    mutate(EMP_RATE = if_else(coalesce(POPULATION, 0L) > 0,
      round(EMPLOYEES / POPULATION * 100, 1), NA_real_)) |>
    select(gemeente_kode, EMPLOYEES, EMP_RATE)
  message(sprintf("  Employment: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  85174NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 6. CBS 83765NED — Average disposable income per person (€/year)
# ============================================================
message("Fetching 83765NED (average income) from CBS...")

income_df <- tryCatch({
  raw <- cbs_get("83765NED",
    filter = "startswith(RegioS,'GM')",
    top = 10000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    latest_p <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }
  val_col <- find_val_col(raw, c("GemiddeldBesteedbaar", "GemiddeldInkomen", "Inkomen", "Besteedbaar"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  result <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value)) |>
    group_by(gemeente_kode) |>
    summarise(AVG_INCOME = round(mean(value, na.rm = TRUE), 0), .groups = "drop")
  message(sprintf("  Income: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  83765NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 7. CBS 85163NED — Education level (higher education %)
# ============================================================
message("Fetching 85163NED (education) from CBS...")

edu_df <- tryCatch({
  raw <- cbs_get("85163NED",
    filter = "startswith(RegioS,'GM')",
    top = 10000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    latest_p <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }
  edu_col <- find_val_col(raw, c("Opleidingsniveau", "Opleiding", "NiveauGroep"))
  val_col  <- find_val_col(raw, c("Bevolking", "Personen", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value))

  if (!is.null(edu_col)) {
    totals  <- df |> filter(grepl("TOTAAL|TOT|^T00", .data[[edu_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |> summarise(total = sum(value, na.rm = TRUE), .groups = "drop")
    higher  <- df |> filter(grepl("HBO|WO|hoog|tertiar|universit", .data[[edu_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |> summarise(n_higher = sum(value, na.rm = TRUE), .groups = "drop")
    result  <- totals |> left_join(higher, by = "gemeente_kode") |>
      mutate(EDU_HIGHER = if_else(total > 0,
        round(coalesce(n_higher, 0) / total * 100, 1), NA_real_)) |>
      select(gemeente_kode, EDU_HIGHER)
  } else {
    result <- df |> group_by(gemeente_kode) |>
      summarise(EDU_HIGHER = round(mean(value, na.rm = TRUE), 1), .groups = "drop")
  }
  message(sprintf("  Education: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  85163NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 8. CBS 82550NED — Housing (woningvoorraad per gemeente)
# ============================================================
message("Fetching 82550NED (housing) from CBS...")

housing_df <- tryCatch({
  raw <- cbs_get("82550NED",
    filter = "startswith(RegioS,'GM')",
    top = 20000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    latest_p <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }
  eig_col <- find_val_col(raw, c("Eigendom", "Eigendom_", "EigendomVerhouding"))
  val_col  <- find_val_col(raw, c("Woningvoorraad", "Woningen", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value))

  if (!is.null(eig_col)) {
    total_dw  <- df |> filter(grepl("TOTAAL|TOT|^T00", .data[[eig_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |> summarise(total = sum(value, na.rm = TRUE), .groups = "drop")
    owner_dw  <- df |> filter(grepl("eigenaar.*bewoner|koop|own", .data[[eig_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |> summarise(owner = sum(value, na.rm = TRUE), .groups = "drop")
    social_dw <- df |> filter(grepl("corporat|huur.*corporat|social|woning.*bouw", .data[[eig_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |> summarise(social = sum(value, na.rm = TRUE), .groups = "drop")

    result <- total_dw |>
      left_join(owner_dw,  by = "gemeente_kode") |>
      left_join(social_dw, by = "gemeente_kode") |>
      mutate(
        OWNER_PCT  = if_else(total > 0, round(coalesce(owner, 0)  / total * 100, 1), NA_real_),
        SOCIAL_PCT = if_else(total > 0, round(coalesce(social, 0) / total * 100, 1), NA_real_),
        DWELLINGS  = as.integer(total)
      ) |>
      select(gemeente_kode, OWNER_PCT, SOCIAL_PCT, DWELLINGS)
  } else {
    result <- df |> group_by(gemeente_kode) |>
      summarise(DWELLINGS = as.integer(sum(value, na.rm = TRUE)), .groups = "drop") |>
      mutate(OWNER_PCT = NA_real_, SOCIAL_PCT = NA_real_)
  }
  message(sprintf("  Housing: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  82550NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 9. CBS 83648NED — Crime (geregistreerde criminaliteit)
# ============================================================
message("Fetching 83648NED (crime) from CBS...")

crime_df <- tryCatch({
  raw <- cbs_get("83648NED",
    filter = "startswith(RegioS,'GM')",
    top = 10000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    latest_p <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }
  val_col <- find_val_col(raw, c("TotaalGeregistreerde", "Misdrijven", "Delicten", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  crimes <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value)) |>
    group_by(gemeente_kode) |>
    summarise(total_crimes = sum(value, na.rm = TRUE), .groups = "drop")

  result <- crimes |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(gemeente_kode, POPULATION)
              else tibble(gemeente_kode = character(), POPULATION = integer()),
              by = "gemeente_kode") |>
    mutate(CRIMES_PER_1K = if_else(coalesce(POPULATION, 0L) > 0,
      round(total_crimes / POPULATION * 1000, 1), NA_real_)) |>
    select(gemeente_kode, CRIMES_PER_1K)
  message(sprintf("  Crime: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  83648NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 10. CBS 37230NED — Population dynamics (births, deaths, migration)
# ============================================================
message("Fetching 37230NED (population dynamics) from CBS...")

pop_dyn_df <- tryCatch({
  raw <- cbs_get("37230NED",
    filter = "startswith(RegioS,'GM')",
    top = 10000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    # Use most recent complete annual period
    annual <- grep("JJ00$", unique(raw[[period_col]]), value = TRUE)
    latest_p <- if (length(annual) > 0) tail(sort(annual), 1) else tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }

  birth_col  <- find_val_col(raw, c("LevensGeboren|Levend|Geboorte|Births"))
  death_col  <- find_val_col(raw, c("Overledenen|Sterfte|Deaths|Sterfgevallen"))
  migr_col   <- find_val_col(raw, c("Migratie|MigratieOverschot|Vestiging|Vertrek"))
  growth_col <- find_val_col(raw, c("BevolkingsGroei|BevGroei|Groei|Growth"))

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS)) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode)

  pop_ref <- if (!is.null(pop_age_df)) pop_age_df |> select(gemeente_kode, POPULATION)
             else tibble(gemeente_kode = character(), POPULATION = integer())

  result <- df |> select(gemeente_kode,
    any_of(c(birth_col, death_col, migr_col, growth_col))) |>
    group_by(gemeente_kode) |>
    summarise(across(everything(), ~ sum(suppressWarnings(as.numeric(.x)), na.rm = TRUE)),
              .groups = "drop") |>
    left_join(pop_ref, by = "gemeente_kode")

  # Compute rates per 1,000
  if (!is.null(birth_col) && birth_col %in% names(result))
    result$BIRTH_RATE <- if_else(coalesce(result$POPULATION, 0L) > 0,
      round(result[[birth_col]] / result$POPULATION * 1000, 1), NA_real_)
  if (!is.null(death_col) && death_col %in% names(result))
    result$DEATH_RATE <- if_else(coalesce(result$POPULATION, 0L) > 0,
      round(result[[death_col]] / result$POPULATION * 1000, 1), NA_real_)
  if (!is.null(migr_col) && migr_col %in% names(result))
    result$NET_MIGRATION <- if_else(coalesce(result$POPULATION, 0L) > 0,
      round(result[[migr_col]] / result$POPULATION * 1000, 1), NA_real_)
  if (!is.null(growth_col) && growth_col %in% names(result))
    result$POP_GROWTH <- if_else(coalesce(result$POPULATION, 0L) > 0,
      round(result[[growth_col]] / result$POPULATION * 100, 2), NA_real_)

  result <- result |>
    select(gemeente_kode,
           any_of(c("BIRTH_RATE", "DEATH_RATE", "NET_MIGRATION", "POP_GROWTH")))

  message(sprintf("  Population dynamics: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  37230NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 11. CBS 81589NED — Business establishments + sector breakdown
# ============================================================
message("Fetching 81589NED (businesses + sectors) from CBS...")

business_df <- NULL
sector_df   <- NULL

tryCatch({
  raw <- cbs_get("81589NED",
    filter = "startswith(RegioS,'GM')",
    top = 100000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    latest_p <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }
  sbi_col <- find_val_col(raw, c("SBI", "Bedrijfstak", "Sector", "Branch"))
  val_col  <- find_val_col(raw, c("Vestigingen", "Bedrijven", "Aantal", "Establishments"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value))

  # Total businesses
  if (!is.null(sbi_col)) {
    total_biz <- df |> filter(grepl("TOTAAL|TOT|^T00|^A000000", .data[[sbi_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |>
      summarise(BUSINESSES = as.integer(sum(value, na.rm = TRUE)), .groups = "drop")
  } else {
    total_biz <- df |> group_by(gemeente_kode) |>
      summarise(BUSINESSES = as.integer(sum(value, na.rm = TRUE)), .groups = "drop")
  }

  business_df <<- total_biz |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(gemeente_kode, POPULATION)
              else tibble(gemeente_kode = character(), POPULATION = integer()),
              by = "gemeente_kode") |>
    mutate(BUSINESSES_PER_1K = if_else(coalesce(POPULATION, 0L) > 0,
      round(BUSINESSES / POPULATION * 1000, 1), NA_real_)) |>
    select(gemeente_kode, BUSINESSES, BUSINESSES_PER_1K)

  # Sector breakdown using SBI section codes
  if (!is.null(sbi_col)) {
    sector_raw <- df |>
      filter(!grepl("TOTAAL|TOT|^T00", .data[[sbi_col]], ignore.case = TRUE)) |>
      mutate(
        sbi_label = toupper(trimws(.data[[sbi_col]])),
        # Map SBI sections to 7 broad categories
        sector_cat = dplyr::case_when(
          grepl("^A|LANDBOUW|AGRICULT|VISSERIJ", sbi_label) ~ "AGR",
          grepl("^B|^C|^D|^E|INDUSTRIE|MANUFACT|ENERGIE|WATER|MIJNBOUW", sbi_label) ~ "MANUF",
          grepl("^F|BOUW|CONSTRUCT", sbi_label) ~ "CONSTRUCT",
          grepl("^G|^H|^I|HANDEL|HORECA|TRANSPORT|VERVOER|TRADE", sbi_label) ~ "TRADE",
          grepl("^J|ICT|INFORMATIE|COMM", sbi_label) ~ "ICT",
          grepl("^K|^L|FINANC|VERZEKER|VASTGOED", sbi_label) ~ "FINANCE",
          grepl("^O|^P|^Q|^R|^S|OVERHEID|ONDERWIJS|ZORG|WELZIJN|PUBLIC|HEALTH", sbi_label) ~ "PUBLIC",
          TRUE ~ NA_character_
        )
      ) |>
      filter(!is.na(sector_cat)) |>
      group_by(gemeente_kode, sector_cat) |>
      summarise(count = sum(value, na.rm = TRUE), .groups = "drop")

    sector_totals <- sector_raw |>
      group_by(gemeente_kode) |>
      summarise(total_wp = sum(count, na.rm = TRUE), .groups = "drop")

    sector_wide <- sector_raw |>
      tidyr::pivot_wider(names_from = sector_cat, values_from = count,
                         names_prefix = "s_", values_fill = 0)

    sector_df <<- sector_totals |>
      left_join(sector_wide, by = "gemeente_kode") |>
      mutate(
        total_wp = pmax(total_wp, 1),
        SECTOR_AGR_PCT       = round(coalesce(s_AGR,      0) / total_wp * 100, 1),
        SECTOR_MANUF_PCT     = round(coalesce(s_MANUF,    0) / total_wp * 100, 1),
        SECTOR_CONSTRUCT_PCT = round(coalesce(s_CONSTRUCT, 0) / total_wp * 100, 1),
        SECTOR_TRADE_PCT     = round(coalesce(s_TRADE,    0) / total_wp * 100, 1),
        SECTOR_ICT_PCT       = round(coalesce(s_ICT,      0) / total_wp * 100, 1),
        SECTOR_FINANCE_PCT   = round(coalesce(s_FINANCE,  0) / total_wp * 100, 1),
        SECTOR_PUBLIC_PCT    = round(coalesce(s_PUBLIC,   0) / total_wp * 100, 1)
      ) |>
      select(gemeente_kode, SECTOR_AGR_PCT, SECTOR_MANUF_PCT, SECTOR_CONSTRUCT_PCT,
             SECTOR_TRADE_PCT, SECTOR_ICT_PCT, SECTOR_FINANCE_PCT, SECTOR_PUBLIC_PCT)
  }

  message(sprintf("  Businesses: %d gemeenten | Sectors: %s",
    nrow(business_df),
    if (!is.null(sector_df)) nrow(sector_df) else "N/A"))
}, error = function(e) { message("  81589NED failed: ", conditionMessage(e)) })


# ============================================================
# 12. CBS 83989NED — Energy demand (gas + electricity per connection)
# ============================================================
message("Fetching 83989NED (energy consumption) from CBS...")

energy_demand_df <- tryCatch({
  raw <- cbs_get("83989NED",
    filter = "startswith(RegioS,'GM')",
    top = 20000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    latest_p <- tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }

  gas_col  <- find_val_col(raw, c("GasVerbruik|Aardgas|Gas"))
  elec_col <- find_val_col(raw, c("ElektriciteitsVerbruik|Elektriciteit|Electriciteit|Stroom"))

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS)) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode)

  result <- df |>
    group_by(gemeente_kode) |>
    summarise(
      GAS_M3_PC  = if (!is.null(gas_col)  && gas_col  %in% names(df))
        round(mean(suppressWarnings(as.numeric(.data[[gas_col]])),  na.rm = TRUE), 0)
        else NA_real_,
      ELEC_KWH_PC = if (!is.null(elec_col) && elec_col %in% names(df))
        round(mean(suppressWarnings(as.numeric(.data[[elec_col]])), na.rm = TRUE), 0)
        else NA_real_,
      .groups = "drop"
    ) |>
    filter(!is.na(GAS_M3_PC) | !is.na(ELEC_KWH_PC))

  message(sprintf("  Energy demand: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  83989NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 13. CBS 82610NED — Renewable energy capacity by municipality
# ============================================================
message("Fetching 82610NED (renewable energy) from CBS...")

green_energy_df <- tryCatch({
  raw <- cbs_get("82610NED",
    filter = "startswith(RegioS,'GM')",
    top = 20000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  if (!is.null(period_col)) {
    annual <- grep("JJ00$", unique(raw[[period_col]]), value = TRUE)
    latest_p <- if (length(annual) > 0) tail(sort(annual), 1) else tail(sort(unique(raw[[period_col]])), 1)
    raw <- raw |> filter(.data[[period_col]] == latest_p)
  }

  type_col  <- find_val_col(raw, c("EnergieBron|TypeRenewable|Bron|TypeEnergie"))
  solar_col <- find_val_col(raw, c("Zon|Solar|PV|Zonne"))
  wind_col  <- find_val_col(raw, c("Wind"))
  cap_col   <- find_val_col(raw, c("Vermogen|Capaciteit|Capacity|MW"))
  if (is.null(cap_col)) cap_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[cap_col]]))) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode, !is.na(value))

  if (!is.null(type_col)) {
    solar <- df |>
      filter(grepl("zon|solar|PV", .data[[type_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |>
      summarise(SOLAR_MW = round(sum(value, na.rm = TRUE) / 1000, 3), .groups = "drop")
    wind <- df |>
      filter(grepl("wind", .data[[type_col]], ignore.case = TRUE)) |>
      group_by(gemeente_kode) |>
      summarise(WIND_MW = round(sum(value, na.rm = TRUE) / 1000, 3), .groups = "drop")
    result <- gemeente_lookup |>
      select(gemeente_kode) |>
      left_join(solar, by = "gemeente_kode") |>
      left_join(wind,  by = "gemeente_kode") |>
      mutate(
        SOLAR_MW           = coalesce(SOLAR_MW, 0),
        WIND_MW            = coalesce(WIND_MW, 0),
        TOTAL_RENEWABLE_MW = round(SOLAR_MW + WIND_MW, 3)
      )
  } else {
    result <- df |>
      group_by(gemeente_kode) |>
      summarise(TOTAL_RENEWABLE_MW = round(sum(value, na.rm = TRUE) / 1000, 3),
                .groups = "drop") |>
      mutate(SOLAR_MW = NA_real_, WIND_MW = NA_real_)
  }

  result <- result |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(gemeente_kode, POPULATION)
              else tibble(gemeente_kode = character(), POPULATION = integer()),
              by = "gemeente_kode") |>
    mutate(RENEWABLE_MW_PER_1K = if_else(coalesce(POPULATION, 0L) > 0,
      round(TOTAL_RENEWABLE_MW / POPULATION * 1000, 3), NA_real_)) |>
    select(gemeente_kode, SOLAR_MW, WIND_MW, TOTAL_RENEWABLE_MW, RENEWABLE_MW_PER_1K) |>
    filter(TOTAL_RENEWABLE_MW > 0 | !is.na(SOLAR_MW))

  message(sprintf("  Renewable energy: %d gemeenten", nrow(result))); result
}, error = function(e) { message("  82610NED failed: ", conditionMessage(e)); NULL })


# ============================================================
# 14. ENTSO-E — NL electricity load & prices (optional)
#     Requires free API key at transparency.entsoe.eu
#     Set env var: ENTSOE_API_KEY
# ============================================================
ENTSOE_KEY <- Sys.getenv("ENTSOE_API_KEY")
entsoe_ts  <- NULL

if (nchar(ENTSOE_KEY) > 0) {
  message("Fetching ENTSO-E NL load + prices...")
  ENTSOE_BASE <- "https://web-api.tp.entsoe.eu/api"
  NL_ZONE     <- "10YNL----------L"

  entsoe_get <- function(doc_type, process_type = NULL, year = 2023) {
    start <- sprintf("%d01010000", year)
    end   <- sprintf("%d01010000", year + 1)
    params <- list(
      securityToken  = ENTSOE_KEY,
      documentType   = doc_type,
      outBiddingZone_Domain = NL_ZONE,
      periodStart    = start,
      periodEnd      = end
    )
    if (!is.null(process_type)) params$processType <- process_type
    url <- httr::modify_url(ENTSOE_BASE, query = params)
    resp <- tryCatch(httr::GET(url, httr::timeout(60)), error = function(e) NULL)
    if (is.null(resp) || httr::http_error(resp)) return(NULL)
    httr::content(resp, "text", encoding = "UTF-8")
  }

  load_xml <- entsoe_get("A65", "A16", year = 2023)   # Actual total load
  price_xml <- entsoe_get("A44", year = 2023)          # Day-ahead prices

  if (!is.null(load_xml)) {
    message("  ENTSO-E load data retrieved (XML parsing required for full integration)")
    entsoe_ts <- list(status = "retrieved", note = "Parse XML for hourly MW values")
  } else {
    message("  ENTSO-E fetch failed or no key provided")
  }
} else {
  message("  ENTSO-E: no API key set (ENTSOE_API_KEY). Skipping live fetch.")
  message("    Register free at https://transparency.entsoe.eu to enable energy time series.")
}


# ============================================================
# 15. Assemble gemeente indicator table
# ============================================================
message("Assembling gemeente indicator table...")

gem_stats <- gemeente_lookup |> select(gemeente_kode)

for (df in list(pop_age_df, foreign_df, unemp_df, emp_df, income_df, edu_df,
                housing_df, crime_df, pop_dyn_df, business_df, sector_df,
                green_energy_df, energy_demand_df)) {
  if (!is.null(df) && "gemeente_kode" %in% names(df))
    gem_stats <- left_join(gem_stats, df, by = "gemeente_kode")
}

message(sprintf("  %d gemeenten × %d indicator columns",
  nrow(gem_stats), ncol(gem_stats) - 1))


# ============================================================
# 16. Urban-rural classification
# ============================================================
classify_urban_rural <- function(pop) {
  dplyr::case_when(pop >= 100000 ~ "Urban",
                   pop >= 20000  ~ "Intermediate",
                   TRUE          ~ "Rural")
}
classify_settlement <- function(pop) {
  dplyr::case_when(pop >= 200000 ~ "Large City",
                   pop >= 50000  ~ "Medium City",
                   pop >= 10000  ~ "Town",
                   TRUE          ~ "Village")
}

gem_full <- gemeente_lookup |>
  left_join(gem_stats, by = "gemeente_kode") |>
  mutate(
    POPULATION         = if ("POPULATION" %in% names(gem_stats))
                           coalesce(POPULATION, 0L) else 0L,
    urban_rural_status = classify_urban_rural(POPULATION),
    settlement_class   = classify_settlement(POPULATION)
  )


# ============================================================
# 17. Build gemeente entries
# ============================================================
message("Building gemeente entries...")

gemeente_entries <- lapply(seq_len(nrow(gem_full)), function(i) {
  row <- gem_full[i, ]
  indicators <- build_indicator_list(row)
  c(list(
    Urban_rural_status = row$urban_rural_status,
    Settlement_class   = row$settlement_class,
    Province           = row$provincie_naam,
    Population         = as.integer(row$POPULATION)
  ), indicators)
}) |> setNames(gem_full$gemeente_kode)


# ============================================================
# 18. Build Provincie entries (aggregate from gemeenten)
# ============================================================
message("Building provincie entries...")

agg_weighted <- function(rows, col) {
  vals <- rows[[col]]; pops <- rows$POPULATION
  ok <- !is.na(vals) & !is.na(pops) & pops > 0
  if (!any(ok)) return(NA_real_)
  if (AGGREGATION_TYPE[[col]] == "sum") sum(vals[ok], na.rm = TRUE)
  else sum(vals[ok] * pops[ok]) / sum(pops[ok])
}

provincie_codes <- unique(gem_full$provincie_kode)
provincie_entries <- lapply(provincie_codes, function(pc) {
  rows <- filter(gem_full, provincie_kode == pc)
  pname <- rows$provincie_naam[1]
  total_pop <- sum(rows$POPULATION, na.rm = TRUE)

  agg <- list()
  for (col in INDICATOR_COLS) {
    if (col == "POPULATION") agg[[col]] <- total_pop
    else if (col %in% names(rows)) agg[[col]] <- agg_weighted(rows, col)
    else agg[[col]] <- NA_real_
  }
  agg_row <- as_tibble(agg)
  indicators <- build_indicator_list(agg_row)

  majority <- function(x) {
    t <- table(x[!is.na(x)])
    if (length(t) == 0) NA_character_ else names(sort(t, decreasing = TRUE))[1]
  }

  c(list(
    Urban_rural_status = majority(rows$urban_rural_status),
    Settlement_class   = majority(rows$settlement_class),
    Province           = pname,
    Population         = as.integer(total_pop)
  ), indicators)
}) |> setNames(provincie_codes)


# ============================================================
# 19. Build Netherlands Total
# ============================================================
message("Building Netherlands Total...")

nl_total_pop <- sum(gem_full$POPULATION, na.rm = TRUE)
nl_row <- list()
for (col in INDICATOR_COLS) {
  if (col == "POPULATION") { nl_row[[col]] <- nl_total_pop; next }
  if (!col %in% names(gem_full)) { nl_row[[col]] <- NA_real_; next }
  vals <- gem_full[[col]]; pops <- gem_full$POPULATION
  ok   <- !is.na(vals) & !is.na(pops) & pops > 0
  nl_row[[col]] <- if (!any(ok)) NA_real_
    else if (AGGREGATION_TYPE[[col]] == "sum") sum(vals[ok])
    else round(sum(vals[ok] * pops[ok]) / sum(pops[ok]), 1)
}
netherlands_total <- build_indicator_list(as_tibble(nl_row))


# ============================================================
# 20. Time series: population (03759NED annual Jan 1)
# ============================================================
message("Fetching population time series from CBS 03759NED...")

pop_ts <- tryCatch({
  ts_periods <- paste0(TS_YEARS, "JJ00")
  raw <- cbs_get("03759NED",
    filter = paste0("startswith(RegioS,'GM') and Geslacht eq 'T001038' and Leeftijd eq 'LTOT'",
                    " and (", paste0("Perioden eq '", ts_periods, "'", collapse = " or "), ")"),
    top = 50000)
  if (is.null(raw)) stop("null")

  val_col <- find_val_col(raw, c("BevolkingOpDeEerste", "Bevolking", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[val_col]])),
           period_id = trimws(Perioden)) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode,
           period_id %in% ts_periods, !is.na(value)) |>
    group_by(gemeente_kode, period_id) |>
    summarise(value = sum(value, na.rm = TRUE), .groups = "drop")

  wide <- df |> tidyr::pivot_wider(names_from = period_id, values_from = value)
  for (p in ts_periods) if (!p %in% names(wide)) wide[[p]] <- NA_real_

  dk_row <- wide |> summarise(across(all_of(ts_periods), ~ sum(.x, na.rm = TRUE)))
  message(sprintf("  Population trend: %d gemeenten × %d years", nrow(wide), length(TS_YEARS)))
  ts_make(wide, dk_row, ts_periods, TS_YEARS)
}, error = function(e) {
  message("  Pop trend failed: ", conditionMessage(e))
  list(years = as.list(TS_YEARS))
})


# ============================================================
# 21. Time series: unemployment rate (85663NED annual)
# ============================================================
message("Fetching unemployment time series from CBS 85663NED...")

unemp_ts <- tryCatch({
  raw <- cbs_get("85663NED", top = 200000)
  if (is.null(raw)) stop("null")

  period_col <- find_val_col(raw, c("Perioden"))
  # Keep only annual periods for our TS_YEARS
  ts_quarters <- paste0(rep(TS_YEARS, each = 4),
                         paste0("KW0", 1:4))
  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS)) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode)

  val_col <- find_val_col(raw, c("Uitkering", "Aantal"))
  if (is.null(val_col)) val_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- df |>
    mutate(value = suppressWarnings(as.numeric(.data[[val_col]])),
           year  = substr(trimws(.data[[period_col]]), 1, 4)) |>
    filter(year %in% TS_YEARS, !is.na(value)) |>
    group_by(gemeente_kode, year) |>
    summarise(unemp = sum(value, na.rm = TRUE), .groups = "drop") |>
    left_join(pop_age_df |> select(gemeente_kode, POPULATION), by = "gemeente_kode") |>
    mutate(value = if_else(coalesce(POPULATION, 0L) > 0,
      round(unemp / POPULATION * 100, 2), NA_real_)) |>
    select(gemeente_kode, year, value)

  wide <- df |> tidyr::pivot_wider(names_from = year, values_from = value)
  for (y in TS_YEARS) if (!y %in% names(wide)) wide[[y]] <- NA_real_

  dk_row <- wide |>
    left_join(pop_age_df |> select(gemeente_kode, POPULATION), by = "gemeente_kode") |>
    summarise(across(all_of(TS_YEARS),
      ~ round(weighted.mean(.x, w = coalesce(POPULATION, 0L), na.rm = TRUE), 2)))
  message(sprintf("  Unemployment trend: %d gemeenten × %d years", nrow(wide), length(TS_YEARS)))
  ts_make(wide, dk_row, TS_YEARS, TS_YEARS)
}, error = function(e) {
  message("  Unemployment trend failed: ", conditionMessage(e))
  list(years = as.list(TS_YEARS))
})


# ============================================================
# 22. Time series: renewable energy (82610NED)
# ============================================================
message("Fetching renewable energy time series from CBS 82610NED...")

renewable_ts <- tryCatch({
  raw <- cbs_get("82610NED",
    filter = paste0("startswith(RegioS,'GM') and (",
      paste0("startswith(Perioden,'", TS_YEARS, "')", collapse = " or "), ")"),
    top = 200000)
  if (is.null(raw)) stop("null")

  cap_col    <- find_val_col(raw, c("Vermogen|Capaciteit|Capacity|MW"))
  period_col <- find_val_col(raw, c("Perioden"))
  if (is.null(cap_col)) cap_col <- names(raw)[sapply(raw, is.numeric)][1]

  df <- raw |>
    mutate(gemeente_kode = extract_gem_code(RegioS),
           value = suppressWarnings(as.numeric(.data[[cap_col]])) / 1000,  # kW → MW
           year  = substr(trimws(.data[[period_col]]), 1, 4)) |>
    filter(gemeente_kode %in% gemeente_lookup$gemeente_kode,
           year %in% TS_YEARS, !is.na(value)) |>
    group_by(gemeente_kode, year) |>
    summarise(value = sum(value, na.rm = TRUE), .groups = "drop")

  wide <- df |> tidyr::pivot_wider(names_from = year, values_from = value)
  for (y in TS_YEARS) if (!y %in% names(wide)) wide[[y]] <- NA_real_

  dk_row <- wide |> summarise(across(all_of(TS_YEARS), ~ sum(.x, na.rm = TRUE)))
  message(sprintf("  Renewable trend: %d gemeenten × %d years", nrow(wide), length(TS_YEARS)))
  ts_make(wide, dk_row, TS_YEARS, TS_YEARS)
}, error = function(e) {
  message("  Renewable trend failed: ", conditionMessage(e))
  list(years = as.list(TS_YEARS))
})


# ============================================================
# 23. Assemble final_json
# ============================================================
final_json <- list(
  "Netherlands Total" = netherlands_total,
  "Provincie"         = lapply(provincie_entries, convert_to_named_list),
  "Gemeente"          = lapply(gemeente_entries,  convert_to_named_list),
  "timeseries"        = list(
    population        = pop_ts,
    unemployment_rate = unemp_ts,
    renewable_energy  = renewable_ts
  ),
  "entsoe" = if (!is.null(entsoe_ts)) entsoe_ts else list(
    status = "pending",
    note   = "Set ENTSOE_API_KEY env var for live NL electricity load + day-ahead prices"
  )
)

message(sprintf("Done. Netherlands Total + %d Provincies + %d Gemeenten ready.",
  length(provincie_entries), length(gemeente_entries)))
