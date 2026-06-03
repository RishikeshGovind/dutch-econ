# ============================================================
# fetch_denmark_data.R
#
# Builds final_json for the Danish Area Profile Builder.
# No API key required — all sources are public.
#
# Sources:
#   DAWA              (api.dataforsyningen.dk)   — kommuner/regioner geography
#   DST               (api.statbank.dk)           — statistics
#   Energi Data Service (api.energidataservice.dk) — renewable energy capacity
#   DMI               (dmigw.govcloud.dk)         — climate baseline indicators
#
# Geographic hierarchy:
#   Region (5)  ←  Kommune (98)
#
# DST notes:
#   - kommunekode in DST = 3-digit string, e.g. "101" for Copenhagen
#   - kommunekode in DAWA = 4-digit zero-padded, e.g. "0101"
#   - We normalise everything to 4-digit in data.json
# ============================================================

library(dplyr)
library(tidyr)
library(tibble)
library(readr)
library(httr)
library(jsonlite)
library(janitor)
library(here)

DST_BASE  <- "https://api.statbank.dk/v1/"
DAWA_BASE <- "https://api.dataforsyningen.dk/"
EDS_BASE  <- "https://api.energidataservice.dk/dataset/"
DMI_BASE  <- "https://dmigw.govcloud.dk/v2/climateData/collections/municipalityValue/items"

# ---- Domain → indicator → internal column mapping ----
VARIABLE_MAP <- list(
  AgeStructure = list(
    `Under 15 years (%)` = "BEV_UNDER15",
    `Over 65 years (%)`  = "BEV_OVER65"
  ),
  LabourMarket = list(
    `Employment rate (%)`    = "EMP_RATE",
    `Unemployment rate (%)`  = "UNEMP_RATE",
    `Out-commuter share (%)` = "COMMUTER_PCT"
  ),
  Economy = list(
    `Employees`        = "EMPLOYEES",
    `Avg income (DKK)` = "AVG_INCOME"
  ),
  Education = list(
    `Secondary education (%)` = "EDU_SEC",
    `Tertiary education (%)`  = "EDU_TER"
  ),
  Migration = list(
    `Foreign citizens (%)` = "FOREIGN_PCT"
  ),
  Housing = list(
    `Owner-occupied (%)`  = "OWNER_PCT",
    `Social housing (%)`  = "SOCIAL_HOUSING_PCT",
    `Dwellings`           = "DWELLINGS"
  ),
  Safety = list(
    `Crimes per 1,000` = "CRIMES_PER_1K"
  ),
  PopulationDynamics = list(
    `Birth rate (per 1,000)`        = "BIRTH_RATE",
    `Death rate (per 1,000)`        = "DEATH_RATE",
    `Natural growth (per 1,000)`    = "NAT_GROWTH",
    `Net migration (per 1,000)`     = "NET_MIGRATION",
    `Population growth (per 1,000)` = "POP_GROWTH"
  ),
  Ancestry = list(
    `Immigrants (%)`    = "ANC_IMMIGRANTS",
    `Descendants (%)`   = "ANC_DESCENDANTS",
    `Danish origin (%)` = "ANC_DANISH"
  ),
  Welfare = list(
    `Welfare dependency (%)`      = "WELFARE_TOTAL",
    `Disability & retirement (%)` = "WELFARE_RETIRE",
    `Cash benefit recipients (%)` = "WELFARE_CASH"
  ),
  Financial = list(
    `Operating expenses/capita (DKK)` = "FIN_OPERATING",
    `Service costs/capita (DKK)`      = "FIN_SERVICE",
    `Long-term debt/capita (DKK)`     = "FIN_DEBT",
    `Capital expenditures/capita (DKK)` = "FIN_CAPITAL",
    `Health care/capita (DKK)`        = "FIN_HEALTH",
    `Education spending/pupil (DKK)`  = "FIN_EDUCATION",
    `Day care/child (DKK)`            = "FIN_DAYCARE",
    `Elderly care/capita (DKK)`       = "FIN_ELDERLY",
    `Equalization grants/capita (DKK)` = "FIN_GRANTS"
  ),
  Health = list(
    `GP utilization (%)` = "GP_UTILIZATION"
  ),
  Businesses = list(
    `Workplaces`           = "WORKPLACES",
    `Workplaces per 1,000` = "WORKPLACES_PER_1K"
  ),
  Vehicles = list(
    `Cars per 1,000` = "CARS_PER_1K"
  ),
  FiscalPolicy = list(
    `Municipal income tax rate (%)` = "TAX_RATE_PCT"
  ),
  IndustrySectors = list(
    `Agriculture, forestry & fishing (%)` = "SECTOR_AGR_PCT",
    `Manufacturing & utilities (%)`        = "SECTOR_MANUF_PCT",
    `Construction (%)`                     = "SECTOR_CONSTRUCT_PCT",
    `Trade & transport (%)`                = "SECTOR_TRADE_PCT",
    `ICT (%)`                              = "SECTOR_ICT_PCT",
    `Finance & insurance (%)`              = "SECTOR_FINANCE_PCT",
    `Public admin, edu & health (%)`       = "SECTOR_PUBLIC_PCT"
  ),
  GreenEnergy = list(
    `Onshore wind capacity (MW)`         = "ONSHORE_WIND_MW",
    `Solar capacity (MW)`                = "SOLAR_MW",
    `Offshore wind capacity (MW)`        = "OFFSHORE_WIND_MW",
    `Total renewable capacity (MW)`      = "TOTAL_RENEWABLE_MW",
    `Renewable capacity (MW per 1,000)`  = "RENEWABLE_MW_PER_1K"
  ),
  ClimateBaseline = list(
    `Mean annual temperature (°C)`  = "MEAN_TEMP_C",
    `Summer days per year (>25°C)`  = "SUMMER_DAYS",
    `Annual precipitation (mm)`     = "ANNUAL_PRECIP_MM",
    `Heating degree days`           = "HEAT_DEG_DAYS"
  ),
  GreenTransition = list(
    `Fossil-linked sector share (%)` = "FOSSIL_SECTOR_PCT",
    `Renewable intensity (MW/1,000)` = "RENEWABLE_MW_PER_1K"
  )
)

AGGREGATION_TYPE <- list(
  POPULATION         = "sum",
  BEV_UNDER15        = "pct",
  BEV_OVER65         = "pct",
  FOREIGN_PCT        = "pct",
  EMP_RATE           = "pct",
  UNEMP_RATE         = "pct",
  COMMUTER_PCT       = "pct",
  EMPLOYEES          = "sum",
  AVG_INCOME         = "pct",
  EDU_SEC            = "pct",
  EDU_TER            = "pct",
  OWNER_PCT          = "pct",
  SOCIAL_HOUSING_PCT = "pct",
  DWELLINGS          = "sum",
  CRIMES_PER_1K      = "pct",
  FIN_GRANTS         = "pct",
  FIN_OPERATING      = "pct",
  FIN_SERVICE        = "pct",
  FIN_DEBT           = "pct",
  FIN_CAPITAL        = "pct",
  FIN_HEALTH         = "pct",
  FIN_EDUCATION      = "pct",
  FIN_DAYCARE        = "pct",
  FIN_ELDERLY        = "pct",
  BIRTH_RATE         = "pct",
  DEATH_RATE         = "pct",
  NAT_GROWTH         = "pct",
  NET_MIGRATION      = "pct",
  POP_GROWTH         = "pct",
  ANC_DANISH         = "pct",
  ANC_IMMIGRANTS     = "pct",
  ANC_DESCENDANTS    = "pct",
  WELFARE_TOTAL      = "pct",
  WELFARE_RETIRE     = "pct",
  WELFARE_CASH       = "pct",
  GP_UTILIZATION     = "pct",
  WORKPLACES          = "sum",
  WORKPLACES_PER_1K   = "pct",
  CARS_PER_1K         = "pct",
  TAX_RATE_PCT        = "pct",
  # IndustrySectors
  SECTOR_AGR_PCT      = "pct",
  SECTOR_MANUF_PCT    = "pct",
  SECTOR_CONSTRUCT_PCT= "pct",
  SECTOR_TRADE_PCT    = "pct",
  SECTOR_ICT_PCT      = "pct",
  SECTOR_FINANCE_PCT  = "pct",
  SECTOR_PUBLIC_PCT   = "pct",
  # GreenEnergy
  ONSHORE_WIND_MW     = "sum",
  SOLAR_MW            = "sum",
  OFFSHORE_WIND_MW    = "sum",
  TOTAL_RENEWABLE_MW  = "sum",
  RENEWABLE_MW_PER_1K = "pct",
  # ClimateBaseline
  MEAN_TEMP_C         = "pct",
  SUMMER_DAYS         = "pct",
  ANNUAL_PRECIP_MM    = "pct",
  HEAT_DEG_DAYS       = "pct",
  # GreenTransition
  FOSSIL_SECTOR_PCT   = "pct"
)
INDICATOR_COLS <- names(AGGREGATION_TYPE)

# ============================================================
# Helpers
# ============================================================
# Caches — populated on first use per table
.tid_cache   <- list()
.label_cache <- list()  # table -> list of variable id -> data.frame(id, text)

get_table_meta <- function(table) {
  if (!is.null(.label_cache[[table]])) return(.label_cache[[table]])
  r <- tryCatch(
    httr::GET(paste0(DST_BASE, "tableinfo/", table), httr::accept_json(), httr::timeout(30)),
    error = function(e) NULL
  )
  if (is.null(r) || httr::http_error(r)) return(NULL)
  info <- jsonlite::fromJSON(httr::content(r, "text", encoding="UTF-8"))
  meta <- list()
  for (i in seq_len(nrow(info$variables))) {
    var_id <- info$variables$id[i]
    vals   <- info$variables$values[[i]]
    if (is.data.frame(vals) && "id" %in% names(vals) && "text" %in% names(vals))
      meta[[var_id]] <- vals[, c("id","text")]
  }
  .label_cache[[table]] <<- meta
  meta
}

latest_tid <- function(table) {
  if (!is.null(.tid_cache[[table]])) return(.tid_cache[[table]])
  meta <- get_table_meta(table)
  if (is.null(meta) || !"Tid" %in% names(meta)) return(NULL)
  val <- tail(meta$Tid$id, 1)
  .tid_cache[[table]] <<- val
  val
}

dst_post <- function(table, variables) {
  # Replace any empty Tid value with the actual latest period for this table
  variables <- lapply(variables, function(v) {
    if (identical(v$code, "Tid") && identical(v$values, list(""))) {
      latest <- latest_tid(table)
      if (!is.null(latest)) v$values <- list(latest)
    }
    v
  })

  body <- list(table=table, format="CSV", delimiter=";", lang="da",
               variables=variables)
  resp <- tryCatch(
    httr::POST(paste0(DST_BASE,"data"),
               httr::content_type_json(),
               body=jsonlite::toJSON(body, auto_unbox=TRUE),
               httr::timeout(120)),
    error = function(e) { message("  POST failed: ", conditionMessage(e)); NULL }
  )
  if (is.null(resp) || httr::http_error(resp)) {
    errtxt <- if (!is.null(resp))
      httr::content(resp, "text", encoding="UTF-8") else "no response"
    message(sprintf("  %s HTTP %s: %s", table,
      if(is.null(resp)) "?" else httr::status_code(resp),
      substr(errtxt, 1, 120)))
    return(NULL)
  }
  txt <- httr::content(resp, "text", encoding="UTF-8")
  df  <- tryCatch(
    readr::read_delim(txt, delim=";", show_col_types=FALSE,
                      locale=readr::locale(encoding="UTF-8")),
    error = function(e) { message("  Parse failed: ", conditionMessage(e)); NULL }
  )
  if (is.null(df)) return(NULL)
  names(df) <- janitor::make_clean_names(names(df))

  # DST returns English labels in the area column; join back to numeric codes.
  # We attach a column `area_code` containing the padded-4-digit kommunekode.
  meta <- get_table_meta(table)
  area_var <- Filter(function(v) grepl("omr|area|bop|arbejdssted", v$code, ignore.case=TRUE),
                     variables)
  if (length(area_var) > 0 && !is.null(meta)) {
    var_id   <- area_var[[1]]$code
    lkp_key  <- tolower(janitor::make_clean_names(var_id))
    area_col <- grep(lkp_key, names(df), value=TRUE, ignore.case=TRUE)[1]
    df$area_code <- NA_character_  # always add column; fill if matching succeeds
    if (!is.na(area_col) && var_id %in% names(meta)) {
      lkp <- meta[[var_id]] |>
        dplyr::mutate(label_clean = tolower(trimws(text)),
                      area_code  = pad4(id)) |>
        dplyr::select(label_clean, area_code)
      df_label <- df[[area_col]] |> tolower() |> trimws()
      df$area_code <- lkp$area_code[match(df_label, lkp$label_clean)]
    }
  } else {
    df$area_code <- NA_character_
  }
  df
}

# 3-digit DST code → 4-digit DAWA-style code
pad4 <- function(x) sprintf("%04d", suppressWarnings(as.integer(x)))

# Extract kommune_kode from a DST data frame.
# Prefers the area_code column injected by dst_post (via label→code join);
# falls back to pad4() of the raw area label if needed.
extract_kommune_kode <- function(df, area_col) {
  if ("area_code" %in% names(df)) return(df$area_code)
  pad4(df[[area_col]])
}

# Identify kommunal-level codes: 3-digit numeric in range 100-860
is_kommunal <- function(x) {
  n <- suppressWarnings(as.integer(x))
  !is.na(n) & nchar(trimws(x)) == 3 & n >= 100 & n <= 860
}

build_indicator_list <- function(row_data) {
  lapply(VARIABLE_MAP, function(domain) {
    lapply(names(domain), function(label) {
      col <- domain[[label]]
      val <- row_data[[col]]
      if (is.null(val) || length(val)==0 || is.na(val)) return(NULL)
      round(as.numeric(val), 2)
    }) |> setNames(names(domain))
  })
}

# Common time series constants — 2012-2024 (13 years, consistent across all tables)
TS_YEARS <- as.character(2012:2024)
TS_K1    <- paste0(TS_YEARS, "K1")   # Jan 1 each year
TS_K4    <- paste0(TS_YEARS, "K4")   # Dec 31 each year
TS_ALL_Q <- unlist(lapply(TS_YEARS, function(y) paste0(y, c("K1","K2","K3","K4"))))

# Helper: assemble a named timeseries list from a wide per-municipality data frame.
# period_ids: column names in wide (e.g. "2012K1" … "2024K1")
# year_labels: axis labels stored in the JSON (e.g. "2012" … "2024")
# dk_row: 1-row df or named numeric vector with DK aggregate per period
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
      wide$kommune_kode
    )
  )
}

convert_to_named_list <- function(x) {
  lapply(x, function(category) {
    if (is.list(category)) category else unname(category)
  })
}

# Helper: map Danish label column → DST ID codes using table metadata
map_labels_to_ids <- function(df, label_col, meta_var) {
  if (!is.null(meta_var)) {
    lkp <- meta_var |> mutate(lc = tolower(trimws(text))) |> dplyr::select(id, lc)
    lkp$id[match(tolower(trimws(df[[label_col]])), lkp$lc)]
  } else {
    df[[label_col]]
  }
}


# ============================================================
# 1. Geography from DAWA
# ============================================================
message("Fetching geography from DAWA...")

# Kommuner (98)
komm_raw <- jsonlite::fromJSON(
  httr::content(httr::GET(paste0(DAWA_BASE,"kommuner?format=json"), httr::timeout(60)),
                "text", encoding="UTF-8"),
  simplifyDataFrame=TRUE
)
kommune_df <- as_tibble(as.data.frame(komm_raw)) |>
  mutate(kommune_kode = pad4(kode), kommune_navn = as.character(navn))

if ("region" %in% names(kommune_df) && is.data.frame(kommune_df$region)) {
  kommune_df$region_kode <- as.character(kommune_df$region$kode)
  kommune_df$region_navn <- as.character(kommune_df$region$navn)
} else {
  reg_map <- c("1081"="Region Hovedstaden","1082"="Region Sjælland",
               "1083"="Region Syddanmark", "1084"="Region Midtjylland",
               "1085"="Region Nordjylland")
  kommune_df$region_kode <- as.character(kommune_df[["regionskode"]])
  kommune_df$region_navn <- reg_map[kommune_df$region_kode]
}

kommune_lookup <- kommune_df |>
  select(kommune_kode, kommune_navn, region_kode, region_navn) |>
  distinct()

message(sprintf("  %d kommuner across %d regions", nrow(kommune_lookup),
                n_distinct(kommune_lookup$region_kode)))

# Regioner (5) — for the Region level data
region_lookup <- kommune_lookup |>
  select(region_kode, region_navn) |>
  distinct()

# DST uses 3-digit codes (e.g. "101") — map to our 4-digit DAWA codes
dst_to_kode <- setNames(kommune_lookup$kommune_kode,
                        as.character(suppressWarnings(as.integer(kommune_lookup$kommune_kode))))


# ============================================================
# 2. FOLK1A — Population + age structure
# ============================================================
message("Fetching FOLK1A (population + age) from DST...")

# Request total + ages 0-14 + ages 65-99 in one call
age_codes <- c("IALT", as.character(0:14), as.character(65:99))

folk1a <- dst_post("FOLK1A", list(
  list(code="OMRÅDE", values=list("*")),
  list(code="ALDER",  values=as.list(age_codes)),
  list(code="KØN",    values=list("TOT")),
  list(code="Tid",    values=list(""))
))

pop_age_df <- NULL
if (!is.null(folk1a)) {
  names(folk1a) <- janitor::make_clean_names(names(folk1a))
  area_c <- grep("omr|area", names(folk1a), value=TRUE, ignore.case=TRUE)[1]
  age_c  <- grep("alder|age", names(folk1a), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal|count", names(folk1a), value=TRUE, ignore.case=TRUE)[1]

  if (!is.na(area_c) && !is.na(age_c) && !is.na(val_c)) {
    f <- folk1a |>
      rename(area=!!area_c, age=!!age_c, value=!!val_c) |>
      mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
             kommune_kode = coalesce(area_code, pad4(area))) |>
      filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

    # Danish labels: "Alder i alt" for total, "X år" for individual years
    totals <- f |>
      filter(grepl("i alt", age, ignore.case=TRUE)) |>
      group_by(kommune_kode) |> summarise(POPULATION = sum(value,na.rm=TRUE),.groups="drop")

    # Extract year number from "X år" pattern
    u15 <- f |>
      filter(!grepl("i alt", age, ignore.case=TRUE)) |>
      mutate(age_n = suppressWarnings(as.integer(gsub("[^0-9]", "", age)))) |>
      filter(!is.na(age_n), age_n <= 14) |>
      group_by(kommune_kode) |> summarise(n_under15=sum(value,na.rm=TRUE),.groups="drop")

    o65 <- f |>
      filter(!grepl("i alt", age, ignore.case=TRUE)) |>
      mutate(age_n = suppressWarnings(as.integer(gsub("[^0-9]", "", age)))) |>
      filter(!is.na(age_n), age_n >= 65) |>
      group_by(kommune_kode) |> summarise(n_over65=sum(value,na.rm=TRUE),.groups="drop")

    pop_age_df <- totals |>
      left_join(u15, by="kommune_kode") |>
      left_join(o65, by="kommune_kode") |>
      mutate(
        BEV_UNDER15 = if_else(POPULATION>0, round(n_under15/POPULATION*100,1), NA_real_),
        BEV_OVER65  = if_else(POPULATION>0, round(n_over65/POPULATION*100,1),  NA_real_)
      ) |>
      select(kommune_kode, POPULATION, BEV_UNDER15, BEV_OVER65)
    message(sprintf("  Population data: %d kommuner", nrow(pop_age_df)))
  }
}


# ============================================================
# 3. FOLK1B — Foreign citizens (STATSB = citizenship)
# ============================================================
message("Fetching FOLK1B (citizenship) from DST...")

folk1b <- dst_post("FOLK1B", list(
  list(code="OMRÅDE", values=list("*")),
  list(code="ALDER",  values=list("IALT")),
  list(code="KØN",    values=list("TOT")),
  list(code="STATSB", values=list("*")),
  list(code="Tid",    values=list(""))
))

foreign_df <- NULL
if (!is.null(folk1b)) {
  names(folk1b) <- janitor::make_clean_names(names(folk1b))
  area_c  <- grep("omr|area", names(folk1b), value=TRUE, ignore.case=TRUE)[1]
  val_c   <- grep("indhold|value|antal|count", names(folk1b), value=TRUE, ignore.case=TRUE)[1]
  stat_c  <- grep("statsb|citizenship|state", names(folk1b), value=TRUE, ignore.case=TRUE)[1]

  if (!is.na(area_c) && !is.na(val_c) && !is.na(stat_c)) {
    fb <- folk1b |>
      rename(area=!!area_c, value=!!val_c, citizenship=!!stat_c) |>
      mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
             kommune_kode = coalesce(area_code, pad4(area))) |>
      filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

    # Danish labels: "I alt" = total, "Danmark" = Danish citizens
    total_cit <- fb |>
      filter(grepl("^i alt$|^in all$", citizenship, ignore.case=TRUE)) |>
      group_by(kommune_kode) |> summarise(cit_total=sum(value,na.rm=TRUE),.groups="drop")

    danish_cit <- fb |>
      filter(grepl("^Danmark$|^Denmark$", citizenship, ignore.case=TRUE)) |>
      group_by(kommune_kode) |> summarise(cit_danish=sum(value,na.rm=TRUE),.groups="drop")

    foreign_df <- total_cit |>
      left_join(danish_cit, by="kommune_kode") |>
      mutate(FOREIGN_PCT = if_else(cit_total>0,
               round((cit_total-coalesce(cit_danish,0))/cit_total*100, 1), NA_real_)) |>
      select(kommune_kode, FOREIGN_PCT)
    message(sprintf("  Foreign citizens: %d kommuner", nrow(foreign_df)))
  }
}


# ============================================================
# 4. AUL01 — Unemployment
# ============================================================
message("Fetching AUL01 (unemployment) from DST...")

aul01 <- dst_post("AUL01", list(
  list(code="OMRÅDE",      values=list("*")),
  list(code="YDELSESTYPE", values=list("TOT")),
  list(code="ALDER",       values=list("TOT")),
  list(code="KØN",         values=list("TOT")),
  list(code="AKASSE",      values=list("TOT")),
  list(code="Tid",         values=list(""))
))

unemp_df <- NULL
if (!is.null(aul01)) {
  names(aul01) <- janitor::make_clean_names(names(aul01))
  area_c <- grep("omr|area", names(aul01), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal|count", names(aul01), value=TRUE, ignore.case=TRUE)[1]

  if (!is.na(area_c) && !is.na(val_c)) {
    unemp_raw <- aul01 |>
      rename(area=!!area_c, value=!!val_c) |>
      mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
             kommune_kode = coalesce(area_code, pad4(area))) |>
      filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

    # AUL01 gives count of unemployed — compute rate against population
    if (!is.null(pop_age_df)) {
      unemp_df <- unemp_raw |>
        group_by(kommune_kode) |> summarise(unemp_count=sum(value,na.rm=TRUE),.groups="drop") |>
        left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
        mutate(UNEMP_RATE = if_else(POPULATION>0,
                             round(unemp_count/POPULATION*100, 1), NA_real_)) |>
        select(kommune_kode, UNEMP_RATE)
    } else {
      unemp_df <- unemp_raw |>
        group_by(kommune_kode) |>
        summarise(UNEMP_RATE = round(sum(value,na.rm=TRUE), 1), .groups="drop")
    }
    message(sprintf("  Unemployment: %d kommuner", nrow(unemp_df)))
  }
}


# ============================================================
# 5. RAS1 — Employment rate
# ============================================================
message("Fetching RAS1 (employment) from DST...")

ras1 <- dst_post("RAS1", list(
  list(code="OMRÅDE", values=list("*")),
  list(code="SOCIO",  values=list("499","500","505")),
  list(code="IETYPE", values=list("999")),
  list(code="ALDER",  values=list("16-19","20-24","25-29","30-34","35-39",
                                   "40-44","45-49","50-54","55-59","60-64","65-66")),
  list(code="KØN",    values=list("M","K")),  # RAS1 has no TOT — sum M+K
  list(code="Tid",    values=list(""))
))

emp_df <- NULL
if (!is.null(ras1)) {
  names(ras1) <- janitor::make_clean_names(names(ras1))
  area_c  <- grep("omr|area", names(ras1), value=TRUE, ignore.case=TRUE)[1]
  val_c   <- grep("indhold|value|antal|count", names(ras1), value=TRUE, ignore.case=TRUE)[1]
  socio_c <- grep("socio", names(ras1), value=TRUE, ignore.case=TRUE)[1]

  if (!is.na(area_c) && !is.na(val_c) && !is.na(socio_c)) {
    ras <- ras1 |>
      rename(area=!!area_c, value=!!val_c, socio=!!socio_c) |>
      mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
             kommune_kode = coalesce(area_code, pad4(area))) |>
      filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

    emp_df <- ras |>
      group_by(kommune_kode) |>
      summarise(
        employed = sum(value[grepl("Besk", socio, ignore.case=TRUE)], na.rm=TRUE),
        total    = sum(value, na.rm=TRUE),
        .groups  = "drop"
      ) |>
      mutate(EMP_RATE = if_else(total>0, round(employed/total*100, 1), NA_real_)) |>
      select(kommune_kode, EMP_RATE)
    message(sprintf("  Employment: %d kommuner", nrow(emp_df)))
  }
}


# ============================================================
# 6. ERHV6 — Employees at local workplaces
# ============================================================
message("Fetching ERHV6 (employees) from DST...")

erhv6 <- dst_post("ERHV6", list(
  list(code="OMRÅDE",      values=list("*")),
  list(code="BRANCHE0710", values=list("TOT")),
  list(code="ARBSTRDK",    values=list("*")),
  list(code="Tid",         values=list(""))
))

emp_local_df <- NULL
if (!is.null(erhv6)) {
  names(erhv6) <- janitor::make_clean_names(names(erhv6))
  area_c <- grep("omr|area|omrade", names(erhv6), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal|count", names(erhv6), value=TRUE, ignore.case=TRUE)[1]

  if (!is.na(area_c) && !is.na(val_c)) {
    emp_local_df <- erhv6 |>
      rename(area=!!area_c, value=!!val_c) |>
      mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
             kommune_kode = coalesce(area_code, pad4(area))) |>
      filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value)) |>
      group_by(kommune_kode) |>
      summarise(EMPLOYEES=sum(value,na.rm=TRUE), .groups="drop")
    message(sprintf("  Employees: %d kommuner", nrow(emp_local_df)))
  }
}


# ============================================================
# 7. HFUDD11 — Education level
# ============================================================
message("Fetching HFUDD11 (education) from DST...")

hfudd <- dst_post("HFUDD11", list(
  list(code="BOPOMR",  values=list("*")),
  list(code="HFUDD",   values=list("TOT","H20","H30","H35","H40","H50")),
  list(code="ALDER",   values=list("TOT")),
  list(code="KØN",     values=list("TOT")),
  list(code="HERKOMST",values=list("TOT")),
  list(code="Tid",     values=list(""))
))

edu_df <- NULL
if (!is.null(hfudd)) {
  names(hfudd) <- janitor::make_clean_names(names(hfudd))
  area_c <- grep("bopomr|omr|area|bop", names(hfudd), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal|count", names(hfudd), value=TRUE, ignore.case=TRUE)[1]
  edu_c  <- grep("hfudd|educ|udd", names(hfudd), value=TRUE, ignore.case=TRUE)[1]

  if (!is.na(area_c) && !is.na(val_c) && !is.na(edu_c)) {
    edu <- hfudd |>
      rename(area=!!area_c, value=!!val_c, edu=!!edu_c) |>
      mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
             kommune_kode = coalesce(area_code, pad4(area))) |>
      filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

    # Danish HFUDD labels: "I alt", "H10 Grundskole", "H20 Gymnasiale uddannelser",
    # "H30 Korte videregående", "H35 Mellemlange videregående", "H40 Bachelor", "H50 Lang videregående"
    edu_total <- edu |>
      filter(grepl("^i alt$|^in all$", edu, ignore.case=TRUE)) |>
      group_by(kommune_kode) |> summarise(edu_total=sum(value,na.rm=TRUE),.groups="drop")

    edu_sec <- edu |>
      filter(grepl("^H20", edu, ignore.case=TRUE)) |>
      group_by(kommune_kode) |> summarise(sec=sum(value,na.rm=TRUE),.groups="drop")

    edu_ter <- edu |>
      filter(grepl("^H3|^H4|^H5", edu, ignore.case=TRUE)) |>
      group_by(kommune_kode) |> summarise(ter=sum(value,na.rm=TRUE),.groups="drop")

    edu_df <- edu_total |>
      left_join(edu_sec, by="kommune_kode") |>
      left_join(edu_ter, by="kommune_kode") |>
      mutate(
        EDU_SEC = if_else(edu_total>0, round(coalesce(sec,0)/edu_total*100,1), NA_real_),
        EDU_TER = if_else(edu_total>0, round(coalesce(ter,0)/edu_total*100,1), NA_real_)
      ) |>
      select(kommune_kode, EDU_SEC, EDU_TER)
    message(sprintf("  Education: %d kommuner", nrow(edu_df)))
  }
}


# ============================================================
# 8a. PEND101 — Out-commuter share
# ============================================================
message("Fetching PEND101 (commuting) from DST...")

commute_df <- tryCatch({
  raw <- dst_post("PEND101", list(
    list(code="OMRÅDE",    values=list("*")),
    list(code="BRANCHE07", values=list("TOT")),
    list(code="PENDLING",  values=list("NAT","UD")),
    list(code="KØN",       values=list("M","K")),   # no TOT — sum M+K
    list(code="Tid",       values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",  names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]
  pend_c <- grep("pendling",  names(raw), value=TRUE, ignore.case=TRUE)[1]

  pend <- raw |>
    rename(area=!!area_c, value=!!val_c, pendling=!!pend_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

  # NAT = residents (denominator), UD = out-commuters (numerator)
  nat <- pend |> filter(grepl("Nat|bopæl|resi", pendling, ignore.case=TRUE)) |>
    group_by(kommune_kode) |> summarise(nat=sum(value,na.rm=TRUE),.groups="drop")
  ud  <- pend |> filter(grepl("Udpend|out", pendling, ignore.case=TRUE)) |>
    group_by(kommune_kode) |> summarise(ud=sum(value,na.rm=TRUE),.groups="drop")

  result <- nat |> left_join(ud, by="kommune_kode") |>
    mutate(COMMUTER_PCT = if_else(nat>0, round(ud/nat*100,1), NA_real_)) |>
    select(kommune_kode, COMMUTER_PCT)
  message(sprintf("  Commuting: %d kommuner", nrow(result))); result
}, error=function(e){ message("  PEND101 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8b. INDKP106 — Average disposable income (DKK per person)
# ============================================================
message("Fetching INDKP106 (income) from DST...")

income_df <- tryCatch({
  raw <- dst_post("INDKP106", list(
    list(code="OMRÅDE",   values=list("*")),
    list(code="ENHED",    values=list("118")),   # avg DKK per person
    list(code="KOEN",     values=list("MOK")),   # both sexes
    list(code="ALDER1",   values=list("00")),    # all ages
    list(code="INDKINTB", values=list("000")),   # all income levels
    list(code="Tid",      values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area", names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  result <- raw |>
    rename(area=!!area_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value)) |>
    group_by(kommune_kode) |>
    summarise(AVG_INCOME = round(mean(value,na.rm=TRUE),0), .groups="drop")
  message(sprintf("  Income: %d kommuner", nrow(result))); result
}, error=function(e){ message("  INDKP106 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8c. BOL101 — Housing (owner-occupied %, social housing %)
# ============================================================
message("Fetching BOL101 (housing) from DST...")

housing_df <- tryCatch({
  # Get exact variable IDs from metadata (OPFØRELSESÅR contains special chars)
  bol_meta <- get_table_meta("BOL101")
  opf_id   <- names(bol_meta)[grepl("pf.*r", names(bol_meta), ignore.case=TRUE)][1]
  if (is.na(opf_id)) opf_id <- "OPFORELSESAR"  # fallback
  opf_vals <- if (!is.null(bol_meta[[opf_id]])) head(bol_meta[[opf_id]]$id, 8) else list("*")

  # 3 types × 2 UDLFORH × 6 EJER × 8 year-bands × 99 = 28,512 cells — well under limit
  raw <- dst_post("BOL101", list(
    list(code="OMRÅDE",    values=list("*")),
    list(code="BEBO",      values=list("1000")),
    list(code="ANVENDELSE",values=list("125","130","140")),
    list(code="UDLFORH",   values=list("EJ","LEJ")),
    list(code="EJER",      values=list("*")),
    list(code=opf_id,      values=as.list(opf_vals)),
    list(code="Tid",       values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area", names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]
  ejer_c <- grep("ejer|owner", names(raw), value=TRUE, ignore.case=TRUE)[1]

  bol <- raw |>
    rename(area=!!area_c, value=!!val_c, ejer=!!ejer_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

  total_dw <- bol |>
    group_by(kommune_kode) |> summarise(total=sum(value,na.rm=TRUE),.groups="drop")
  # Privatpersoner = owner-occupied, Almene boligselskaber = social housing
  owner  <- bol |> filter(grepl("Privatpersoner|private.*person|owner", ejer, ignore.case=TRUE)) |>
    group_by(kommune_kode) |> summarise(owner=sum(value,na.rm=TRUE),.groups="drop")
  social <- bol |> filter(grepl("Almene|social|public|almen", ejer, ignore.case=TRUE)) |>
    group_by(kommune_kode) |> summarise(social=sum(value,na.rm=TRUE),.groups="drop")

  result <- total_dw |>
    left_join(owner,  by="kommune_kode") |>
    left_join(social, by="kommune_kode") |>
    mutate(
      OWNER_PCT          = if_else(total>0, round(coalesce(owner,0)/total*100,1), NA_real_),
      SOCIAL_HOUSING_PCT = if_else(total>0, round(coalesce(social,0)/total*100,1), NA_real_),
      DWELLINGS          = as.integer(total)
    ) |>
    select(kommune_kode, OWNER_PCT, SOCIAL_HOUSING_PCT, DWELLINGS)
  message(sprintf("  Housing: %d kommuner", nrow(result))); result
}, error=function(e){ message("  BOL101 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8d. STRAF11 — Crimes per 1,000 residents
# ============================================================
message("Fetching STRAF11 (crime) from DST...")

crime_df <- tryCatch({
  raw <- dst_post("STRAF11", list(
    list(code="OMRÅDE",    values=list("*")),
    list(code="OVERTRÆD",  values=list("TOT")),
    list(code="Tid",       values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area", names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  crimes <- raw |>
    rename(area=!!area_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value)) |>
    group_by(kommune_kode) |>
    summarise(total_crimes=sum(value,na.rm=TRUE), .groups="drop")

  result <- crimes |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(kommune_kode, POPULATION)
              else tibble(kommune_kode=character(), POPULATION=integer()),
              by="kommune_kode") |>
    mutate(CRIMES_PER_1K = if_else(coalesce(POPULATION,0L)>0,
                             round(total_crimes/POPULATION*1000, 1), NA_real_)) |>
    select(kommune_kode, CRIMES_PER_1K)
  message(sprintf("  Crime: %d kommuner", nrow(result))); result
}, error=function(e){ message("  STRAF11 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8e. NGLK — Municipal finances key figures
# ============================================================
message("Fetching NGLK (municipal finances) from DST...")

# NGLK BNØGLE codes → internal column names
NGLK_CODES <- c(DRI="FIN_OPERATING", SER="FIN_SERVICE", LAN="FIN_DEBT",
                 ANL="FIN_CAPITAL",  SUN="FIN_HEALTH",  FOL="FIN_EDUCATION",
                 DAG="FIN_DAYCARE",  ÆLD="FIN_ELDERLY", UDL="FIN_GRANTS")

finance_df <- tryCatch({
  raw <- dst_post("NGLK", list(
    list(code="OMRÅDE",     values=list("*")),
    list(code="BNØGLE",     values=as.list(names(NGLK_CODES))),
    list(code="BRUTNETUDG", values=list("NET")),
    list(code="PRISENHED",  values=list("AARPRIS")),
    list(code="Tid",        values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c  <- grep("omr|area|omr_de", names(raw), value=TRUE, ignore.case=TRUE)[1]
  bn_c    <- grep("bnøgle|n.gle|key|noegle", names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c   <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  fin <- raw |>
    rename(area=!!area_c, bnoegle=!!bn_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub("[. ]","",gsub(",",".",value)))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

  # Pivot: one row per kommune, one column per BNØGLE code
  # The bnoegle column contains Danish labels — join back via metadata
  nglk_meta <- get_table_meta("NGLK")
  if (!is.null(nglk_meta$`BNØGLE`)) {
    lkp <- nglk_meta$`BNØGLE` |>
      mutate(label_clean = tolower(trimws(text))) |>
      dplyr::select(id, label_clean)
    fin$bn_code <- lkp$id[match(tolower(trimws(fin$bnoegle)), lkp$label_clean)]
  } else {
    fin$bn_code <- fin$bnoegle
  }

  fin_wide <- fin |>
    filter(!is.na(bn_code), bn_code %in% names(NGLK_CODES)) |>
    group_by(kommune_kode, bn_code) |>
    summarise(value = mean(value, na.rm=TRUE), .groups="drop") |>
    tidyr::pivot_wider(names_from=bn_code, values_from=value) |>
    rename_with(~ NGLK_CODES[.x], .cols = tidyselect::any_of(names(NGLK_CODES)))

  # Ensure all financial columns exist
  for (col in unname(NGLK_CODES)) {
    if (!col %in% names(fin_wide)) fin_wide[[col]] <- NA_real_
  }
  message(sprintf("  Finance: %d kommuner", nrow(fin_wide)))
  fin_wide
}, error=function(e){ message("  NGLK failed: ", conditionMessage(e)); NULL })


# ============================================================
# 8f. BEV107 — Population dynamics (births, deaths, migration)
# ============================================================
message("Fetching BEV107 (population dynamics) from DST...")

pop_dyn_df <- tryCatch({
  raw <- dst_post("BEV107", list(
    list(code="OMRÅDE",    values=list("*")),
    list(code="BEVÆGELSE", values=list("B01A","B02","B03","B04","B10","B11")),
    list(code="KØN",       values=list("M","K")),
    list(code="Tid",       values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  bev_c  <- grep("bev",                names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  bev <- raw |>
    rename(area=!!area_c, bev_label=!!bev_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

  # Map Danish BEVÆGELSE labels → codes
  bev107_meta <- get_table_meta("BEV107")
  if (!is.null(bev107_meta[["BEVÆGELSE"]])) {
    lkp <- bev107_meta[["BEVÆGELSE"]] |>
      mutate(label_clean = tolower(trimws(text))) |>
      dplyr::select(id, label_clean)
    bev$bev_code <- lkp$id[match(tolower(trimws(bev$bev_label)), lkp$label_clean)]
  } else {
    bev$bev_code <- bev$bev_label
  }

  bev_wide <- bev |>
    filter(!is.na(bev_code)) |>
    group_by(kommune_kode, bev_code) |>
    summarise(v = sum(value, na.rm=TRUE), .groups="drop") |>
    tidyr::pivot_wider(names_from=bev_code, values_from=v)

  for (col in c("B01A","B02","B03","B04","B10","B11")) {
    if (!col %in% names(bev_wide)) bev_wide[[col]] <- NA_real_
  }

  result <- bev_wide |>
    mutate(
      denom         = coalesce(B01A, 0),
      BIRTH_RATE    = if_else(denom>0, round(coalesce(B02,0)/denom*1000, 1), NA_real_),
      DEATH_RATE    = if_else(denom>0, round(coalesce(B03,0)/denom*1000, 1), NA_real_),
      NAT_GROWTH    = if_else(denom>0, round(coalesce(B04,0)/denom*1000, 1), NA_real_),
      NET_MIGRATION = if_else(denom>0, round(coalesce(B10,0)/denom*1000, 1), NA_real_),
      POP_GROWTH    = if_else(denom>0, round(coalesce(B11,0)/denom*1000, 1), NA_real_)
    ) |>
    select(kommune_kode, BIRTH_RATE, DEATH_RATE, NAT_GROWTH, NET_MIGRATION, POP_GROWTH)
  message(sprintf("  Population dynamics: %d kommuner", nrow(result)))
  result
}, error=function(e){ message("  BEV107 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8g. FOLK1E — Ancestry (Danish origin, immigrants, descendants)
# ============================================================
message("Fetching FOLK1E (ancestry) from DST...")

ancestry_df <- tryCatch({
  raw <- dst_post("FOLK1E", list(
    list(code="OMRÅDE",   values=list("*")),
    list(code="ALDER",    values=list("IALT")),
    list(code="KØN",      values=list("TOT")),
    list(code="HERKOMST", values=list("TOT","1","24","25","34","35")),
    list(code="Tid",      values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  herk_c <- grep("herkomst|anc",       names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  anc <- raw |>
    rename(area=!!area_c, herk_label=!!herk_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

  # Map Danish HERKOMST labels → codes
  folk1e_meta <- get_table_meta("FOLK1E")
  if (!is.null(folk1e_meta[["HERKOMST"]])) {
    lkp <- folk1e_meta[["HERKOMST"]] |>
      mutate(label_clean = tolower(trimws(text))) |>
      dplyr::select(id, label_clean)
    anc$herk_code <- lkp$id[match(tolower(trimws(anc$herk_label)), lkp$label_clean)]
  } else {
    anc$herk_code <- anc$herk_label
  }

  total_anc <- anc |>
    filter(herk_code == "TOT") |>
    group_by(kommune_kode) |> summarise(total=sum(value,na.rm=TRUE),.groups="drop")
  danish_anc <- anc |>
    filter(herk_code == "1") |>
    group_by(kommune_kode) |> summarise(danish=sum(value,na.rm=TRUE),.groups="drop")
  immigrant_anc <- anc |>
    filter(herk_code %in% c("24","25")) |>
    group_by(kommune_kode) |> summarise(immigrants=sum(value,na.rm=TRUE),.groups="drop")
  descendant_anc <- anc |>
    filter(herk_code %in% c("34","35")) |>
    group_by(kommune_kode) |> summarise(descendants=sum(value,na.rm=TRUE),.groups="drop")

  result <- total_anc |>
    left_join(danish_anc,     by="kommune_kode") |>
    left_join(immigrant_anc,  by="kommune_kode") |>
    left_join(descendant_anc, by="kommune_kode") |>
    mutate(
      ANC_DANISH      = if_else(total>0, round(coalesce(danish,0)/total*100,1),      NA_real_),
      ANC_IMMIGRANTS  = if_else(total>0, round(coalesce(immigrants,0)/total*100,1),  NA_real_),
      ANC_DESCENDANTS = if_else(total>0, round(coalesce(descendants,0)/total*100,1), NA_real_)
    ) |>
    select(kommune_kode, ANC_DANISH, ANC_IMMIGRANTS, ANC_DESCENDANTS)
  message(sprintf("  Ancestry: %d kommuner", nrow(result)))
  result
}, error=function(e){ message("  FOLK1E failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8h. AUK01 — Welfare dependency (public benefit recipients)
# ============================================================
message("Fetching AUK01 (welfare) from DST...")

welfare_df <- tryCatch({
  raw <- dst_post("AUK01", list(
    list(code="OMRÅDE",      values=list("*")),
    list(code="YDELSESTYPE", values=list("TOTUSU","FP","TP","KT","KH")),
    list(code="KØN",         values=list("TOT")),
    list(code="ALDER",       values=list("TOT")),
    list(code="Tid",         values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  ydel_c <- grep("ydelse|benefit",     names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  wel <- raw |>
    rename(area=!!area_c, ydel_label=!!ydel_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

  # Map Danish YDELSESTYPE labels → codes
  auk01_meta <- get_table_meta("AUK01")
  if (!is.null(auk01_meta[["YDELSESTYPE"]])) {
    lkp <- auk01_meta[["YDELSESTYPE"]] |>
      mutate(label_clean = tolower(trimws(text))) |>
      dplyr::select(id, label_clean)
    wel$ydel_code <- lkp$id[match(tolower(trimws(wel$ydel_label)), lkp$label_clean)]
  } else {
    wel$ydel_code <- wel$ydel_label
  }

  total_wel  <- wel |> filter(ydel_code == "TOTUSU") |>
    group_by(kommune_kode) |> summarise(welf_total=sum(value,na.rm=TRUE),.groups="drop")
  retire_wel <- wel |> filter(ydel_code %in% c("FP","TP")) |>
    group_by(kommune_kode) |> summarise(welf_retire=sum(value,na.rm=TRUE),.groups="drop")
  cash_wel   <- wel |> filter(ydel_code %in% c("KT","KH")) |>
    group_by(kommune_kode) |> summarise(welf_cash=sum(value,na.rm=TRUE),.groups="drop")

  result <- total_wel |>
    left_join(retire_wel, by="kommune_kode") |>
    left_join(cash_wel,   by="kommune_kode") |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(kommune_kode, POPULATION)
              else tibble(kommune_kode=character(), POPULATION=integer()),
              by="kommune_kode") |>
    mutate(
      WELFARE_TOTAL  = if_else(coalesce(POPULATION,0L)>0,
                         round(coalesce(welf_total,0)/POPULATION*100, 1), NA_real_),
      WELFARE_RETIRE = if_else(coalesce(POPULATION,0L)>0,
                         round(coalesce(welf_retire,0)/POPULATION*100, 1), NA_real_),
      WELFARE_CASH   = if_else(coalesce(POPULATION,0L)>0,
                         round(coalesce(welf_cash,0)/POPULATION*100, 1), NA_real_)
    ) |>
    select(kommune_kode, WELFARE_TOTAL, WELFARE_RETIRE, WELFARE_CASH)
  message(sprintf("  Welfare: %d kommuner", nrow(result)))
  result
}, error=function(e){ message("  AUK01 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8i. SYGP1 — Health: persons with GP contacts (%)
# ============================================================
message("Fetching SYGP1 (GP health contacts) from DST...")

health_df <- tryCatch({
  raw <- dst_post("SYGP1", list(
    list(code="OMRÅDE",     values=list("*")),
    list(code="YDELSESART", values=list("130")),  # general medical treatment total
    list(code="ALERAMS",    values=list("IALT")),
    list(code="KØN",        values=list("TOT")),
    list(code="Tid",        values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  result <- raw |>
    rename(area=!!area_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value)) |>
    group_by(kommune_kode) |>
    summarise(gp_persons = sum(value, na.rm=TRUE), .groups="drop") |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(kommune_kode, POPULATION)
              else tibble(kommune_kode=character(), POPULATION=integer()),
              by="kommune_kode") |>
    mutate(GP_UTILIZATION = if_else(coalesce(POPULATION,0L)>0,
                              round(gp_persons/POPULATION*100, 1), NA_real_)) |>
    select(kommune_kode, GP_UTILIZATION)
  message(sprintf("  Health (GP): %d kommuner", nrow(result)))
  result
}, error=function(e){ message("  SYGP1 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8j. ERHV5 — Workplaces by municipality
# ============================================================
message("Fetching ERHV5 (workplaces) from DST...")

business_df <- tryCatch({
  raw <- dst_post("ERHV5", list(
    list(code="OMRÅDE", values=list("*")),
    list(code="SEKTOR", values=list("1015","1020","1025","1030","1035","1040","1045")),
    list(code="Tid",    values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  result <- raw |>
    rename(area=!!area_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value)) |>
    group_by(kommune_kode) |>
    summarise(WORKPLACES = as.integer(sum(value, na.rm=TRUE)), .groups="drop") |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(kommune_kode, POPULATION)
              else tibble(kommune_kode=character(), POPULATION=integer()),
              by="kommune_kode") |>
    mutate(WORKPLACES_PER_1K = if_else(coalesce(POPULATION,0L)>0,
                                 round(WORKPLACES/POPULATION*1000, 1), NA_real_)) |>
    select(kommune_kode, WORKPLACES, WORKPLACES_PER_1K)
  message(sprintf("  Workplaces: %d kommuner", nrow(result)))
  result
}, error=function(e){ message("  ERHV5 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 8k. BIL54 — Passenger cars per 1,000 residents
# ============================================================
message("Fetching BIL54 (passenger cars) from DST...")

cars_df <- tryCatch({
  raw <- dst_post("BIL54", list(
    list(code="OMRÅDE",  values=list("*")),
    list(code="BILTYPE", values=list("4000101002")),  # passenger cars, total
    list(code="BRUG",    values=list("1000")),         # total (all uses)
    list(code="DRIV",    values=list("20200")),        # total propellant
    list(code="Tid",     values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  result <- raw |>
    rename(area=!!area_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area))) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value)) |>
    group_by(kommune_kode) |>
    summarise(total_cars = sum(value, na.rm=TRUE), .groups="drop") |>
    left_join(if (!is.null(pop_age_df)) pop_age_df |> select(kommune_kode, POPULATION)
              else tibble(kommune_kode=character(), POPULATION=integer()),
              by="kommune_kode") |>
    mutate(CARS_PER_1K = if_else(coalesce(POPULATION,0L)>0,
                           round(total_cars/POPULATION*1000, 1), NA_real_)) |>
    select(kommune_kode, CARS_PER_1K)
  message(sprintf("  Cars: %d kommuner", nrow(result)))
  result
}, error=function(e){ message("  BIL54 failed: ",conditionMessage(e)); NULL })


# ============================================================
# 7a. PSKAT — Municipal income tax rate (FiscalPolicy domain)
# ============================================================
message("Fetching PSKAT (municipal tax rates) from DST...")

tax_rate_df <- tryCatch({
  raw <- dst_post("PSKAT", list(
    list(code="OMRÅDE",  values=list("*")),
    list(code="SKATPCT", values=list("KOM")),
    list(code="Tid",     values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area", names(raw), value=TRUE, ignore.case=TRUE)[1]
  # Use last column — PSKAT column order is OMRÅDE, SKATPCT, TID, INDHOLD
  val_c <- tail(names(raw)[!names(raw) %in% c("area_code")], 1)

  raw |>
    rename(area=!!area_c, value=!!val_c) |>
    mutate(
      value        = suppressWarnings(as.numeric(gsub(",",".",value))),
      kommune_kode = coalesce(area_code, pad4(area)),
      # DST stores rate in hundredths of a percent (2360 = 23.60%) when lang=da
      TAX_RATE_PCT = round(ifelse(!is.na(value) & value > 100, value / 100, value), 2)
    ) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(TAX_RATE_PCT)) |>
    select(kommune_kode, TAX_RATE_PCT)
}, error=function(e){ message("  PSKAT failed: ", conditionMessage(e)); NULL })

if (!is.null(tax_rate_df))
  message(sprintf("  Tax rates: %d kommuner", nrow(tax_rate_df)))


# ============================================================
# 7b. ERHV6 sector breakdown — IndustrySectors domain
# ============================================================
message("Fetching ERHV6 sector breakdown from DST...")

sector_df <- tryCatch({
  # ARBSTRDK has no "IALT" total — request all sizes and sum below
  raw <- dst_post("ERHV6", list(
    list(code="OMRÅDE",      values=list("*")),
    list(code="BRANCHE0710", values=list("*")),
    list(code="ARBSTRDK",    values=list("*")),
    list(code="Tid",         values=list(""))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))

  area_c    <- grep("omr|area",              names(raw), value=TRUE, ignore.case=TRUE)[1]
  branch_c  <- grep("branche|industry|branch",names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c     <- grep("indhold|value|antal",   names(raw), value=TRUE, ignore.case=TRUE)[1]

  df <- raw |>
    rename(area=!!area_c, branch=!!branch_c, value=!!val_c) |>
    mutate(
      value        = suppressWarnings(as.numeric(gsub(",",".",value))),
      kommune_kode = coalesce(area_code, pad4(area)),
      # Map Danish branch labels to the 10-group DB07 codes
      branch_id    = suppressWarnings(as.integer(gsub("[^0-9]", "", branch)))
    ) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value), !is.na(branch_id))

  # Total workplaces per municipality — sum sectors 1-10 directly.
  # The TOT row has branch_id=NA after gsub and is filtered out, so we can't use it.
  totals <- df |>
    filter(branch_id >= 1, branch_id <= 10) |>
    group_by(kommune_kode) |>
    summarise(total_wp = sum(value, na.rm=TRUE), .groups="drop")

  # Sector-level counts (DB07 10-group codes 1-10)
  sectors <- df |>
    filter(branch_id >= 1, branch_id <= 10) |>
    group_by(kommune_kode, branch_id) |>
    summarise(count = sum(value, na.rm=TRUE), .groups="drop") |>
    tidyr::pivot_wider(names_from=branch_id, values_from=count,
                       names_prefix="s", values_fill=0)

  result <- totals |>
    left_join(sectors, by="kommune_kode") |>
    mutate(
      total_wp = pmax(total_wp, 1),   # avoid /0
      SECTOR_AGR_PCT       = round(coalesce(s1, 0) / total_wp * 100, 1),
      SECTOR_MANUF_PCT     = round(coalesce(s2, 0) / total_wp * 100, 1),
      SECTOR_CONSTRUCT_PCT = round(coalesce(s3, 0) / total_wp * 100, 1),
      SECTOR_TRADE_PCT     = round(coalesce(s4, 0) / total_wp * 100, 1),
      SECTOR_ICT_PCT       = round(coalesce(s5, 0) / total_wp * 100, 1),
      SECTOR_FINANCE_PCT   = round(coalesce(s6, 0) / total_wp * 100, 1),
      SECTOR_PUBLIC_PCT    = round(coalesce(s9, 0) / total_wp * 100, 1),
      # Fossil-linked: manufacturing/utilities (s2) + trade/transport (s4)
      FOSSIL_SECTOR_PCT    = round((coalesce(s2,0) + coalesce(s4,0)) / total_wp * 100, 1)
    ) |>
    select(kommune_kode, SECTOR_AGR_PCT, SECTOR_MANUF_PCT, SECTOR_CONSTRUCT_PCT,
           SECTOR_TRADE_PCT, SECTOR_ICT_PCT, SECTOR_FINANCE_PCT, SECTOR_PUBLIC_PCT,
           FOSSIL_SECTOR_PCT)

  message(sprintf("  Sector data: %d kommuner", nrow(result)))
  result
}, error=function(e){ message("  ERHV6 sector failed: ", conditionMessage(e)); NULL })


# ============================================================
# 7c. Energi Data Service — GreenEnergy domain
# ============================================================
message("Fetching CapacityPerMunicipality from Energi Data Service...")

green_energy_df <- tryCatch({
  # Pull latest month for all municipalities
  url  <- paste0(EDS_BASE, "CapacityPerMunicipality?limit=200&offset=0",
                 "&sort=Month%20desc")
  resp <- httr::GET(url, httr::accept_json(), httr::timeout(60))
  if (httr::http_error(resp)) stop(paste("HTTP", httr::status_code(resp)))

  records <- jsonlite::fromJSON(httr::content(resp,"text",encoding="UTF-8"),
                                simplifyDataFrame=TRUE)$records

  if (is.null(records) || nrow(records) == 0) stop("no records")

  # Keep only the most recent month
  latest_month <- max(records$Month, na.rm=TRUE)
  rec <- records |>
    dplyr::filter(Month == latest_month) |>
    dplyr::mutate(
      kommune_kode  = pad4(as.integer(MunicipalityNo)),
      ONSHORE_WIND_MW  = round(as.numeric(OnshoreWindCapacity),  2),
      SOLAR_MW         = round(as.numeric(SolarPowerCapacity),   2),
      OFFSHORE_WIND_MW = round(as.numeric(OffshoreWindCapacity), 2),
      TOTAL_RENEWABLE_MW = round(ONSHORE_WIND_MW + SOLAR_MW + OFFSHORE_WIND_MW, 2)
    ) |>
    dplyr::filter(kommune_kode %in% kommune_lookup$kommune_kode) |>
    dplyr::select(kommune_kode, ONSHORE_WIND_MW, SOLAR_MW, OFFSHORE_WIND_MW,
                  TOTAL_RENEWABLE_MW)

  # Add per-capita metric using population from pop_age_df
  if (!is.null(pop_age_df)) {
    rec <- rec |>
      left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
      mutate(
        RENEWABLE_MW_PER_1K = if_else(
          coalesce(POPULATION, 0L) > 0,
          round(TOTAL_RENEWABLE_MW / POPULATION * 1000, 3),
          NA_real_)
      ) |>
      select(-POPULATION)
  } else {
    rec$RENEWABLE_MW_PER_1K <- NA_real_
  }

  message(sprintf("  Green energy: %d kommuner (data as of %s)",
                  nrow(rec), latest_month))
  rec
}, error=function(e){ message("  EDS capacity failed: ", conditionMessage(e)); NULL })


# ============================================================
# 7d. DMI — ClimateBaseline domain
# ============================================================
message("Fetching climate baseline from DMI...")

dmi_fetch_param <- function(param_id, year = 2023) {
  # DMI municipalityValue with annual resolution for cumulative parameters
  from  <- sprintf("%d-01-01T00:00:00Z", year)
  to    <- sprintf("%d-12-31T23:59:59Z", year)
  url   <- paste0(DMI_BASE,
    "?parameterId=", param_id,
    "&datetime=", utils::URLencode(paste0(from, "/", to)),
    "&timeResolution=year",
    "&limit=200")
  resp  <- httr::GET(url, httr::accept_json(), httr::timeout(60))
  if (httr::http_error(resp)) return(NULL)
  feats <- jsonlite::fromJSON(httr::content(resp,"text",encoding="UTF-8"),
                              simplifyDataFrame=TRUE)$features
  if (is.null(feats) || length(feats) == 0) return(NULL)
  props <- feats$properties
  if (is.null(props)) return(NULL)
  tibble::tibble(
    kommune_kode = pad4(as.integer(props$municipalityId)),
    value        = as.numeric(props$value)
  ) |>
    dplyr::group_by(kommune_kode) |>
    dplyr::summarise(value = mean(value, na.rm=TRUE), .groups="drop") |>
    dplyr::rename(!!param_id := value)
}

climate_df <- tryCatch({
  temp_df   <- dmi_fetch_param("mean_temp",                2023)
  summer_df <- dmi_fetch_param("no_summer_days",           2023)
  precip_df <- dmi_fetch_param("acc_precip",               2023)
  hdd_df    <- dmi_fetch_param("acc_heating_degree_days_17", 2023)

  all_dfs <- list(temp_df, summer_df, precip_df, hdd_df)
  non_null <- Filter(Negate(is.null), all_dfs)
  if (length(non_null) == 0) stop("all DMI fetches failed")

  result <- Reduce(function(a, b) full_join(a, b, by="kommune_kode"), non_null) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode) |>
    rename_with(~ case_when(
      . == "mean_temp"                  ~ "MEAN_TEMP_C",
      . == "no_summer_days"             ~ "SUMMER_DAYS",
      . == "acc_precip"                 ~ "ANNUAL_PRECIP_MM",
      . == "acc_heating_degree_days_17" ~ "HEAT_DEG_DAYS",
      TRUE ~ .
    ))

  message(sprintf("  Climate baseline: %d kommuner, %d parameters",
                  nrow(result), ncol(result) - 1))
  result
}, error=function(e){ message("  DMI climate failed: ", conditionMessage(e)); NULL })


# ============================================================
# 8. Assemble kommunal indicator table
# ============================================================
message("Assembling kommunal indicator table...")

komm_stats <- kommune_lookup |> select(kommune_kode)

for (df in list(pop_age_df, foreign_df, unemp_df, emp_df, emp_local_df, edu_df,
                commute_df, income_df, housing_df, crime_df, finance_df,
                pop_dyn_df, ancestry_df, welfare_df, health_df, business_df, cars_df,
                tax_rate_df, sector_df, green_energy_df, climate_df)) {
  if (!is.null(df) && "kommune_kode" %in% names(df))
    komm_stats <- left_join(komm_stats, df, by="kommune_kode")
}
message(sprintf("  %d kommuner × %d indicator columns",
  nrow(komm_stats), ncol(komm_stats)-1))


# ============================================================
# 9. Urban-rural classification from population
# ============================================================
classify_urban_rural <- function(pop) {
  dplyr::case_when(pop >= 20000 ~ "Urban",
                   pop >=  5000 ~ "Intermediate",
                   TRUE         ~ "Rural")
}
classify_settlement <- function(pop) {
  dplyr::case_when(pop >= 50000 ~ "Large City",
                   pop >= 10000 ~ "Small City",
                   pop >=  2000 ~ "Town",
                   TRUE         ~ "Village")
}

komm_full <- kommune_lookup |>
  left_join(komm_stats, by="kommune_kode") |>
  mutate(
    POPULATION = if ("POPULATION" %in% names(komm_stats))
                   coalesce(POPULATION, 0L) else 0L,
    urban_rural_status = classify_urban_rural(POPULATION),
    settlement_class   = classify_settlement(POPULATION),
    density_class      = "Unknown"
  )


# ============================================================
# 10. Build Kommune entries
# ============================================================
message("Building Kommune entries...")

kommune_entries <- lapply(seq_len(nrow(komm_full)), function(i) {
  row <- komm_full[i, ]
  indicators <- build_indicator_list(row)
  c(list(Urban_rural_status = row$urban_rural_status,
         Settlement_class   = row$settlement_class,
         Density_class      = row$density_class,
         Region             = row$region_navn,
         Population         = as.integer(row$POPULATION)),
    indicators)
}) |> setNames(komm_full$kommune_kode)


# ============================================================
# 11. Build Region entries (aggregate from kommuner)
# ============================================================
message("Building Region entries...")

agg_weighted <- function(rows, col) {
  vals <- rows[[col]]; pops <- rows$POPULATION
  ok <- !is.na(vals) & !is.na(pops) & pops > 0
  if (!any(ok)) return(NA_real_)
  if (AGGREGATION_TYPE[[col]] == "sum") sum(vals[ok], na.rm=TRUE)
  else sum(vals[ok]*pops[ok])/sum(pops[ok])
}

region_codes <- unique(komm_full$region_kode)
region_entries <- lapply(region_codes, function(rc) {
  rows <- filter(komm_full, region_kode == rc)
  rname <- rows$region_navn[1]
  total_pop <- sum(rows$POPULATION, na.rm=TRUE)

  agg <- list()
  for (col in INDICATOR_COLS) {
    if (col == "POPULATION") agg[[col]] <- total_pop
    else if (col %in% names(rows)) agg[[col]] <- agg_weighted(rows, col)
    else agg[[col]] <- NA_real_
  }
  agg_row <- as_tibble(agg)
  indicators <- build_indicator_list(agg_row)

  majority <- function(x) { t<-table(x[!is.na(x)]); if(length(t)==0) NA_character_ else names(sort(t,decreasing=TRUE))[1] }

  c(list(Urban_rural_status = majority(rows$urban_rural_status),
         Settlement_class   = majority(rows$settlement_class),
         Density_class      = majority(rows$density_class),
         Region             = rname,
         Population         = as.integer(total_pop)),
    indicators)
}) |> setNames(region_codes)


# ============================================================
# 12. Build Denmark Total
# ============================================================
message("Building Denmark Total...")

total_pop <- sum(komm_full$POPULATION, na.rm=TRUE)
dk_row <- list()
for (col in INDICATOR_COLS) {
  if (col == "POPULATION") { dk_row[[col]] <- total_pop; next }
  if (!col %in% names(komm_full)) { dk_row[[col]] <- NA_real_; next }
  vals <- komm_full[[col]]; pops <- komm_full$POPULATION
  ok   <- !is.na(vals) & !is.na(pops) & pops > 0
  dk_row[[col]] <- if (!any(ok)) NA_real_
    else if (AGGREGATION_TYPE[[col]]=="sum") sum(vals[ok])
    else round(sum(vals[ok]*pops[ok])/sum(pops[ok]), 1)
}
denmark_total <- build_indicator_list(as_tibble(dk_row))


# ============================================================
# 13. Time series: population (FOLK1A K1 — Jan 1 each year)
# ============================================================
message("Fetching FOLK1A K1 time series (population)...")

pop_ts <- tryCatch({
  raw <- dst_post("FOLK1A", list(
    list(code="OMRÅDE", values=list("*")),
    list(code="ALDER",  values=list("IALT")),
    list(code="KØN",    values=list("TOT")),
    list(code="Tid",    values=as.list(TS_K1))
  ))
  if (is.null(raw)) stop("null")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  tid_c  <- grep("tid|time|kvart",     names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  f1a_meta <- get_table_meta("FOLK1A")
  df <- raw |>
    rename(area=!!area_c, tid=!!tid_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area)),
           period_id = map_labels_to_ids(pick(tid), "tid", f1a_meta$Tid)) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode,
           period_id %in% TS_K1, !is.na(value))

  wide <- df |>
    group_by(kommune_kode, period_id) |>
    summarise(value = sum(value, na.rm=TRUE), .groups="drop") |>
    tidyr::pivot_wider(names_from=period_id, values_from=value)
  for (p in TS_K1) if (!p %in% names(wide)) wide[[p]] <- NA_real_

  dk_row <- wide |> summarise(across(all_of(TS_K1), ~ sum(.x, na.rm=TRUE)))
  message(sprintf("  Population trend: %d kommuner × %d years", nrow(wide), length(TS_YEARS)))
  ts_make(wide, dk_row, TS_K1, TS_YEARS)
}, error=function(e){ message("  Pop trend failed: ", conditionMessage(e)); list(years=as.list(TS_YEARS)) })


# ============================================================
# 14. Time series: foreign citizens % (FOLK1B K1)
# ============================================================
message("Fetching FOLK1B K1 time series (foreign citizens %)...")

foreign_ts <- tryCatch({
  raw <- dst_post("FOLK1B", list(
    list(code="OMRÅDE", values=list("*")),
    list(code="ALDER",  values=list("IALT")),
    list(code="KØN",    values=list("TOT")),
    list(code="STATSB", values=list("*")),
    list(code="Tid",    values=as.list(TS_K1))
  ))
  if (is.null(raw)) stop("null")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c  <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  stat_c  <- grep("statsb|citizen|state", names(raw), value=TRUE, ignore.case=TRUE)[1]
  tid_c   <- grep("tid|time|kvart",     names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c   <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  f1b_meta <- get_table_meta("FOLK1B")
  df <- raw |>
    rename(area=!!area_c, statsb=!!stat_c, tid=!!tid_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area)),
           period_id = map_labels_to_ids(pick(tid), "tid", f1b_meta$Tid)) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode,
           period_id %in% TS_K1, !is.na(value))

  totals <- df |>
    filter(grepl("^i alt$|^in all$|^total$", statsb, ignore.case=TRUE)) |>
    group_by(kommune_kode, period_id) |>
    summarise(total=sum(value,na.rm=TRUE), .groups="drop")
  danish <- df |>
    filter(grepl("^Danmark$|^Denmark$", statsb, ignore.case=TRUE)) |>
    group_by(kommune_kode, period_id) |>
    summarise(danish=sum(value,na.rm=TRUE), .groups="drop")

  pct_long <- totals |>
    left_join(danish, by=c("kommune_kode","period_id")) |>
    mutate(value = if_else(total>0,
             round((total - coalesce(danish,0))/total*100, 1), NA_real_)) |>
    select(kommune_kode, period_id, value)

  wide <- pct_long |>
    tidyr::pivot_wider(names_from=period_id, values_from=value)
  for (p in TS_K1) if (!p %in% names(wide)) wide[[p]] <- NA_real_

  dk_row <- wide |>
    left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
    summarise(across(all_of(TS_K1),
      ~ round(weighted.mean(.x, w=coalesce(POPULATION,0L), na.rm=TRUE), 1)))
  message(sprintf("  Foreign % trend: %d kommuner × %d years", nrow(wide), length(TS_YEARS)))
  ts_make(wide, dk_row, TS_K1, TS_YEARS)
}, error=function(e){ message("  Foreign trend failed: ", conditionMessage(e)); list(years=as.list(TS_YEARS)) })


# ============================================================
# 15. Time series: unemployment rate % (AUL01 annual)
# ============================================================
message("Fetching AUL01 time series (unemployment rate)...")

unemp_ts <- tryCatch({
  raw <- dst_post("AUL01", list(
    list(code="OMRÅDE",      values=list("*")),
    list(code="YDELSESTYPE", values=list("TOT")),
    list(code="ALDER",       values=list("TOT")),
    list(code="KØN",         values=list("TOT")),
    list(code="AKASSE",      values=list("TOT")),
    list(code="Tid",         values=as.list(TS_YEARS))
  ))
  if (is.null(raw)) stop("null")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  tid_c  <- grep("^tid$|^time$|^year$", names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  aul_meta <- get_table_meta("AUL01")
  df <- raw |>
    rename(area=!!area_c, tid=!!tid_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area)),
           period_id = map_labels_to_ids(pick(tid), "tid", aul_meta$Tid)) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode,
           period_id %in% TS_YEARS, !is.na(value)) |>
    group_by(kommune_kode, period_id) |>
    summarise(unemp = sum(value, na.rm=TRUE), .groups="drop") |>
    left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
    mutate(value = if_else(coalesce(POPULATION,0L)>0,
                    round(unemp/POPULATION*100, 2), NA_real_)) |>
    select(kommune_kode, period_id, value)

  wide <- df |>
    tidyr::pivot_wider(names_from=period_id, values_from=value)
  for (p in TS_YEARS) if (!p %in% names(wide)) wide[[p]] <- NA_real_

  dk_row <- wide |>
    left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
    summarise(across(all_of(TS_YEARS),
      ~ round(weighted.mean(.x, w=coalesce(POPULATION,0L), na.rm=TRUE), 2)))
  message(sprintf("  Unemployment trend: %d kommuner × %d years", nrow(wide), length(TS_YEARS)))
  ts_make(wide, dk_row, TS_YEARS, TS_YEARS)
}, error=function(e){ message("  Unemployment trend failed: ", conditionMessage(e)); list(years=as.list(TS_YEARS)) })


# ============================================================
# 16. Time series: crime rate per 1,000 (STRAF11 quarterly → annual sum)
# ============================================================
message("Fetching STRAF11 time series (crime rate)...")

crime_ts <- tryCatch({
  raw <- dst_post("STRAF11", list(
    list(code="OMRÅDE",   values=list("*")),
    list(code="OVERTRÆD", values=list("TOT")),
    list(code="Tid",      values=as.list(TS_ALL_Q))
  ))
  if (is.null(raw)) stop("null")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  tid_c  <- grep("tid|time|kvart",     names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  straf_meta <- get_table_meta("STRAF11")
  df <- raw |>
    rename(area=!!area_c, tid=!!tid_c, value=!!val_c) |>
    mutate(value = suppressWarnings(as.numeric(gsub(",",".",value))),
           kommune_kode = coalesce(area_code, pad4(area)),
           period_id = map_labels_to_ids(pick(tid), "tid", straf_meta$Tid),
           year = substr(period_id, 1, 4)) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode,
           year %in% TS_YEARS, !is.na(value)) |>
    group_by(kommune_kode, year) |>
    summarise(annual_crimes = sum(value, na.rm=TRUE), .groups="drop") |>
    left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
    mutate(value = if_else(coalesce(POPULATION,0L)>0,
                    round(annual_crimes/POPULATION*1000, 2), NA_real_)) |>
    select(kommune_kode, year, value)

  wide <- df |>
    tidyr::pivot_wider(names_from=year, values_from=value)
  for (y in TS_YEARS) if (!y %in% names(wide)) wide[[y]] <- NA_real_

  dk_row <- wide |>
    left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
    summarise(across(all_of(TS_YEARS),
      ~ round(weighted.mean(.x, w=coalesce(POPULATION,0L), na.rm=TRUE), 2)))
  message(sprintf("  Crime trend: %d kommuner × %d years", nrow(wide), length(TS_YEARS)))
  ts_make(wide, dk_row, TS_YEARS, TS_YEARS)
}, error=function(e){ message("  Crime trend failed: ", conditionMessage(e)); list(years=as.list(TS_YEARS)) })


# ============================================================
# 17. Time series: disposable income trend (INDKP106, last 12 years)
# ============================================================
message("Fetching INDKP106 time series (income trend)...")

income_ts <- tryCatch({
  ts_meta  <- get_table_meta("INDKP106")
  ts_years <- tail(ts_meta$Tid$id, 12)

  raw <- dst_post("INDKP106", list(
    list(code="OMRÅDE",   values=list("*")),
    list(code="ENHED",    values=list("118")),
    list(code="KOEN",     values=list("MOK")),
    list(code="ALDER1",   values=list("00")),
    list(code="INDKINTB", values=list("000")),
    list(code="Tid",      values=as.list(ts_years))
  ))
  if (is.null(raw)) stop("null response")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  tid_c  <- grep("^tid$|^time$",       names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  df <- raw |>
    rename(area=!!area_c, tid=!!tid_c, value=!!val_c) |>
    mutate(
      value        = suppressWarnings(as.numeric(gsub("[. ]","",gsub(",",".",value)))),
      kommune_kode = coalesce(area_code, pad4(area))
    ) |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode, !is.na(value))

  # Map Danish Tid labels → year IDs
  if (!is.null(ts_meta$Tid)) {
    lkp <- ts_meta$Tid |>
      mutate(label_clean = tolower(trimws(text))) |>
      dplyr::select(id, label_clean)
    df$year_id <- lkp$id[match(tolower(trimws(df$tid)), lkp$label_clean)]
  } else {
    df$year_id <- df$tid
  }

  wide <- df |>
    filter(year_id %in% ts_years) |>
    group_by(kommune_kode, year_id) |>
    summarise(value = round(mean(value, na.rm=TRUE), 0), .groups="drop") |>
    tidyr::pivot_wider(names_from=year_id, values_from=value)

  # Compute population-weighted Denmark average for each year
  dk_avg <- wide |>
    left_join(pop_age_df |> select(kommune_kode, POPULATION), by="kommune_kode") |>
    summarise(across(all_of(ts_years),
      ~ round(weighted.mean(.x, w=coalesce(POPULATION, 0L), na.rm=TRUE), 0)))

  # Build named list: years vector + one entry per kommune + "000" = DK average
  result <- c(
    list(years = as.list(ts_years)),
    list("000" = as.list(unname(as.numeric(dk_avg[1, ts_years])))),
    setNames(
      lapply(seq_len(nrow(wide)), function(i)
        as.list(unname(as.numeric(wide[i, ts_years])))),
      wide$kommune_kode
    )
  )
  message(sprintf("  Income trend: %d kommuner × %d years", nrow(wide), length(ts_years)))
  result
}, error=function(e){ message("  Income trend failed: ", conditionMessage(e)); list(years=list()) })


# ============================================================
# Phase 2c. NGLK time-series — SFC debt & fiscal dynamics
# ============================================================
message("Fetching NGLK time series (SFC debt dynamics)...")

SFC_TS_YEARS <- as.character(2012:2024)
SFC_CODES    <- c("LAN","DRI","UDL","ANL","SER")  # debt, operating, grants, capital, service

sfc_timeseries <- tryCatch({
  raw <- dst_post("NGLK", list(
    list(code="OMRÅDE",     values=list("*")),
    list(code="BNØGLE",     values=as.list(SFC_CODES)),
    list(code="BRUTNETUDG", values=list("NET")),
    list(code="PRISENHED",  values=list("AARPRIS")),
    list(code="Tid",        values=as.list(SFC_TS_YEARS))
  ))
  if (is.null(raw)) stop("null")
  names(raw) <- janitor::make_clean_names(names(raw))
  area_c <- grep("omr|area",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  bn_c   <- grep("bnøgle|n.gle|noegle|key", names(raw), value=TRUE, ignore.case=TRUE)[1]
  tid_c  <- grep("tid|time",           names(raw), value=TRUE, ignore.case=TRUE)[1]
  val_c  <- grep("indhold|value|antal", names(raw), value=TRUE, ignore.case=TRUE)[1]

  df <- raw |>
    rename(area=!!area_c, bnoegle=!!bn_c, tid=!!tid_c, value=!!val_c) |>
    mutate(value        = suppressWarnings(as.numeric(gsub("[. ]","",gsub(",",".",value)))),
           kommune_kode = coalesce(area_code, pad4(area)))

  # Map Danish labels → codes
  nglk_meta <- get_table_meta("NGLK")
  if (!is.null(nglk_meta$`BNØGLE`)) {
    lkp <- nglk_meta$`BNØGLE` |> mutate(lc=tolower(trimws(text)))
    df$bn_code <- lkp$id[match(tolower(trimws(df$bnoegle)), lkp$lc)]
  } else {
    df$bn_code <- df$bnoegle
  }
  # Map Danish year labels → numeric year
  tid_meta <- get_table_meta("NGLK")
  if (!is.null(tid_meta$Tid)) {
    tlkp <- tid_meta$Tid |> mutate(lc=tolower(trimws(text)))
    df$year_id <- tlkp$id[match(tolower(trimws(df$tid)), tlkp$lc)]
  } else {
    df$year_id <- df$tid
  }

  df <- df |>
    filter(kommune_kode %in% kommune_lookup$kommune_kode,
           bn_code %in% SFC_CODES,
           year_id %in% SFC_TS_YEARS,
           !is.na(value))

  # Build one ts_make-style list per BNØGLE code
  result <- lapply(setNames(SFC_CODES, tolower(SFC_CODES)), function(code) {
    sub <- df |> filter(bn_code == code)
    wide <- sub |>
      group_by(kommune_kode, year_id) |>
      summarise(value=mean(value, na.rm=TRUE), .groups="drop") |>
      tidyr::pivot_wider(names_from=year_id, values_from=value)
    for (y in SFC_TS_YEARS) if (!y %in% names(wide)) wide[[y]] <- NA_real_
    dk_row <- wide |> summarise(across(all_of(SFC_TS_YEARS), ~mean(.x,na.rm=TRUE)))
    ts_make(wide, dk_row, SFC_TS_YEARS, SFC_TS_YEARS)
  })
  message(sprintf("  SFC time series: %d codes × %d years", length(SFC_CODES), length(SFC_TS_YEARS)))
  result
}, error=function(e){ message("  SFC TS failed: ", conditionMessage(e)); NULL })


# ============================================================
# 14. Assemble final_json
# ============================================================
final_json <- list(
  "Denmark Total" = denmark_total,
  "Region"        = lapply(region_entries,  convert_to_named_list),
  "Kommune"       = lapply(kommune_entries, convert_to_named_list),
  "timeseries"    = list(
    income            = income_ts,
    population        = pop_ts,
    foreign_pct       = foreign_ts,
    unemployment_rate = unemp_ts,
    crime_rate        = crime_ts
  ),
  "sfc_timeseries" = if (!is.null(sfc_timeseries)) sfc_timeseries else list()
)

message(sprintf("Done. Denmark Total + %d Regions + %d Kommuner ready.",
  length(region_entries), length(kommune_entries)))
