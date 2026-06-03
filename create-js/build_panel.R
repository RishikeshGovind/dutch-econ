# ============================================================
# build_panel.R
#
# Builds a gemeente-level energy panel dataset for the
# Predict-Then-Optimize PhD demo (Maastricht UM).
#
# Output: data/panel_dataset.csv
#   One row per gemeente per year (2012-2023)
#   Columns: gas consumption, electricity consumption,
#            renewable capacity, solar/wind breakdown,
#            population, employment, sector shares
#
# Sources:
#   CBS 83989NED — Energy consumption dwellings per gemeente
#   CBS 82610NED — Renewable energy capacity per gemeente
#   CBS 03759NED — Population per gemeente
#   CBS 85174NED — Employment per gemeente
# ============================================================

source("create-js/config.R")

OUTPUT_PATH <- "data/panel_dataset.csv"
YEARS       <- 2012:2023

# ---- CBS OData helper (same as in fetch_netherlands_data.R) ----
cbs_get_panel <- function(table, filter = "", top = 200000) {
  url <- paste0(CBS_BASE, table, "/TypedDataSet?$top=", top)
  if (nchar(filter) > 0)
    url <- paste0(url, "&$filter=", utils::URLencode(filter, reserved = TRUE))
  resp <- tryCatch(
    httr::GET(url, httr::accept_json(), httr::timeout(180)),
    error = function(e) { message("  GET failed (", table, "): ", conditionMessage(e)); NULL }
  )
  if (is.null(resp) || httr::http_error(resp)) {
    if (!is.null(resp)) message(sprintf("  %s HTTP %s", table, httr::status_code(resp)))
    return(NULL)
  }
  raw <- tryCatch(
    jsonlite::fromJSON(httr::content(resp, "text", encoding = "UTF-8"))$value,
    error = function(e) { message("  Parse failed (", table, "): ", conditionMessage(e)); NULL }
  )
  if (is.null(raw) || length(raw) == 0) return(NULL)
  as_tibble(raw)
}

extract_gem_code <- function(x) {
  sprintf("%04d", suppressWarnings(as.integer(sub("^GM0*", "", trimws(x)))))
}

find_val_col <- function(df, patterns) {
  for (p in patterns) {
    hits <- grep(p, names(df), value = TRUE, ignore.case = TRUE)
    if (length(hits) > 0) return(hits[1])
  }
  NULL
}

year_from_period <- function(p) substr(trimws(p), 1, 4)


# ============================================================
# 1. Energy consumption (83989NED) — gas + electricity per dwelling
# ============================================================
message("Fetching energy consumption time series (83989NED)...")

energy_raw <- cbs_get_panel("83989NED",
  filter = "startswith(RegioS,'GM')")

energy_panel <- NULL
if (!is.null(energy_raw)) {
  period_col <- find_val_col(energy_raw, c("Perioden"))
  gas_col    <- find_val_col(energy_raw, c("GasVerbruik", "Aardgas", "Gas"))
  elec_col   <- find_val_col(energy_raw, c("ElektriciteitsVerbruik", "Elektriciteit", "Electriciteit", "Stroom"))

  if (!is.null(period_col)) {
    energy_panel <- energy_raw |>
      mutate(
        gemeente_kode = extract_gem_code(RegioS),
        year          = as.integer(year_from_period(.data[[period_col]]))
      ) |>
      filter(year %in% YEARS) |>
      group_by(gemeente_kode, year) |>
      summarise(
        gas_m3_pc   = if (!is.null(gas_col))
          mean(suppressWarnings(as.numeric(.data[[gas_col]])),  na.rm = TRUE) else NA_real_,
        elec_kwh_pc = if (!is.null(elec_col))
          mean(suppressWarnings(as.numeric(.data[[elec_col]])), na.rm = TRUE) else NA_real_,
        .groups = "drop"
      )
    message(sprintf("  Energy demand: %d gemeente-year rows", nrow(energy_panel)))
  }
} else {
  message("  83989NED unavailable — skipping energy demand")
}


# ============================================================
# 2. Renewable energy capacity (82610NED)
# ============================================================
message("Fetching renewable energy time series (82610NED)...")

renewable_raw <- cbs_get_panel("82610NED",
  filter = "startswith(RegioS,'GM')")

renewable_panel <- NULL
if (!is.null(renewable_raw)) {
  period_col <- find_val_col(renewable_raw, c("Perioden"))
  type_col   <- find_val_col(renewable_raw, c("EnergieBron", "TypeEnergie", "Bron"))
  cap_col    <- find_val_col(renewable_raw, c("Vermogen", "Capaciteit", "Capacity", "MW"))
  if (is.null(cap_col)) cap_col <- names(renewable_raw)[sapply(renewable_raw, is.numeric)][1]

  if (!is.null(period_col)) {
    df_ren <- renewable_raw |>
      mutate(
        gemeente_kode = extract_gem_code(RegioS),
        year          = as.integer(year_from_period(.data[[period_col]])),
        cap_mw        = suppressWarnings(as.numeric(.data[[cap_col]])) / 1000  # kW → MW
      ) |>
      filter(year %in% YEARS, !is.na(cap_mw))

    if (!is.null(type_col)) {
      solar <- df_ren |>
        filter(grepl("zon|solar|PV", .data[[type_col]], ignore.case = TRUE)) |>
        group_by(gemeente_kode, year) |>
        summarise(solar_mw = sum(cap_mw, na.rm = TRUE), .groups = "drop")
      wind  <- df_ren |>
        filter(grepl("wind", .data[[type_col]], ignore.case = TRUE)) |>
        group_by(gemeente_kode, year) |>
        summarise(wind_mw  = sum(cap_mw, na.rm = TRUE), .groups = "drop")
      total <- df_ren |>
        group_by(gemeente_kode, year) |>
        summarise(total_renewable_mw = sum(cap_mw, na.rm = TRUE), .groups = "drop")
      renewable_panel <- total |>
        left_join(solar, by = c("gemeente_kode", "year")) |>
        left_join(wind,  by = c("gemeente_kode", "year"))
    } else {
      renewable_panel <- df_ren |>
        group_by(gemeente_kode, year) |>
        summarise(total_renewable_mw = sum(cap_mw, na.rm = TRUE), .groups = "drop") |>
        mutate(solar_mw = NA_real_, wind_mw = NA_real_)
    }
    message(sprintf("  Renewable capacity: %d gemeente-year rows", nrow(renewable_panel)))
  }
} else {
  message("  82610NED unavailable — skipping renewable energy")
}


# ============================================================
# 3. Population (03759NED)
# ============================================================
message("Fetching population time series (03759NED)...")

pop_raw <- cbs_get_panel("03759NED",
  filter = paste0("startswith(RegioS,'GM') and Geslacht eq 'T001038' and Leeftijd eq 'LTOT'",
                  " and (", paste0("startswith(Perioden,'", YEARS, "')", collapse = " or "), ")"))

pop_panel <- NULL
if (!is.null(pop_raw)) {
  period_col <- "Perioden"
  val_col    <- find_val_col(pop_raw, c("BevolkingOpDeEerste", "Bevolking", "Inwoners", "Aantal"))
  if (is.null(val_col)) val_col <- names(pop_raw)[sapply(pop_raw, is.numeric)][1]

  pop_panel <- pop_raw |>
    mutate(
      gemeente_kode = extract_gem_code(RegioS),
      year          = as.integer(year_from_period(Perioden)),
      population    = suppressWarnings(as.numeric(.data[[val_col]]))
    ) |>
    filter(year %in% YEARS, !is.na(population)) |>
    group_by(gemeente_kode, year) |>
    summarise(population = sum(population, na.rm = TRUE), .groups = "drop")
  message(sprintf("  Population: %d gemeente-year rows", nrow(pop_panel)))
} else {
  message("  03759NED unavailable — skipping population")
}


# ============================================================
# 4. Employment / jobs (85174NED)
# ============================================================
message("Fetching employment time series (85174NED)...")

emp_raw <- cbs_get_panel("85174NED",
  filter = "startswith(RegioS,'GM')")

emp_panel <- NULL
if (!is.null(emp_raw)) {
  period_col <- find_val_col(emp_raw, c("Perioden"))
  val_col    <- find_val_col(emp_raw, c("Banen", "Werkzame", "Werknemers", "Aantal"))
  if (is.null(val_col)) val_col <- names(emp_raw)[sapply(emp_raw, is.numeric)][1]

  if (!is.null(period_col)) {
    emp_panel <- emp_raw |>
      mutate(
        gemeente_kode = extract_gem_code(RegioS),
        year          = as.integer(year_from_period(.data[[period_col]])),
        employees     = suppressWarnings(as.numeric(.data[[val_col]]))
      ) |>
      filter(year %in% YEARS, !is.na(employees)) |>
      group_by(gemeente_kode, year) |>
      summarise(employees = sum(employees, na.rm = TRUE), .groups = "drop")
    message(sprintf("  Employment: %d gemeente-year rows", nrow(emp_panel)))
  }
} else {
  message("  85174NED unavailable — skipping employment")
}


# ============================================================
# 5. Assemble panel
# ============================================================
message("Assembling energy panel...")

# Start with a complete gemeente × year grid
base_panel <- tryCatch({
  gem_years <- expand.grid(
    gemeente_kode = unique(c(
      if (!is.null(energy_panel))     energy_panel$gemeente_kode,
      if (!is.null(renewable_panel))  renewable_panel$gemeente_kode,
      if (!is.null(pop_panel))        pop_panel$gemeente_kode
    )),
    year = YEARS,
    stringsAsFactors = FALSE
  ) |> as_tibble()
  gem_years
}, error = function(e) {
  tibble(gemeente_kode = character(), year = integer())
})

panel <- base_panel

if (!is.null(pop_panel))
  panel <- left_join(panel, pop_panel, by = c("gemeente_kode", "year"))
if (!is.null(emp_panel))
  panel <- left_join(panel, emp_panel, by = c("gemeente_kode", "year"))
if (!is.null(energy_panel))
  panel <- left_join(panel, energy_panel, by = c("gemeente_kode", "year"))
if (!is.null(renewable_panel))
  panel <- left_join(panel, renewable_panel, by = c("gemeente_kode", "year"))


# ============================================================
# 6. Derived variables for predict-then-optimize modelling
# ============================================================
panel <- panel |>
  arrange(gemeente_kode, year) |>
  group_by(gemeente_kode) |>
  mutate(
    # Per-capita renewable capacity (MW per 1,000 people)
    renewable_mw_per_1k = if_else(
      coalesce(population, 0) > 0,
      round(coalesce(total_renewable_mw, 0) / population * 1000, 4),
      NA_real_
    ),
    # Year-on-year renewable growth
    renewable_growth = (total_renewable_mw - lag(total_renewable_mw)) /
                       (lag(total_renewable_mw) + 0.001),
    # Solar share of renewables
    solar_share = if_else(
      coalesce(total_renewable_mw, 0) > 0,
      round(coalesce(solar_mw, 0) / total_renewable_mw, 3),
      NA_real_
    ),
    # Green transition score: renewable MW per unit of fossil energy demand
    green_score = if_else(
      coalesce(gas_m3_pc, 0) > 0,
      round(coalesce(total_renewable_mw, 0) /
              (population * gas_m3_pc / 1e6 + 0.001), 2),
      NA_real_
    ),
    # Settlement class
    settlement_class = dplyr::case_when(
      coalesce(population, 0) >= 200000 ~ "Large City",
      coalesce(population, 0) >= 50000  ~ "Medium City",
      coalesce(population, 0) >= 10000  ~ "Town",
      !is.na(population)                ~ "Village",
      TRUE                              ~ NA_character_
    ),
    urban_rural = dplyr::case_when(
      coalesce(population, 0) >= 100000 ~ "Urban",
      coalesce(population, 0) >= 20000  ~ "Intermediate",
      !is.na(population)                ~ "Rural",
      TRUE                              ~ NA_character_
    )
  ) |>
  ungroup()


# ============================================================
# 7. Save
# ============================================================
message("Saving energy panel dataset...")
if (!dir.exists("data")) dir.create("data")
readr::write_csv(panel, OUTPUT_PATH)

message(sprintf("Done. Panel saved to %s", OUTPUT_PATH))
message(sprintf("  Rows: %s | Columns: %d | Gemeenten: %d | Years: %s",
  format(nrow(panel), big.mark = ","),
  ncol(panel),
  n_distinct(panel$gemeente_kode),
  paste(sort(unique(panel$year)), collapse = ", ")))

# Quick renewable energy summary
if (!is.null(renewable_panel)) {
  message("\nRenewable capacity summary (latest year):")
  panel |>
    filter(year == max(YEARS)) |>
    summarise(
      n_gemeenten           = n(),
      total_solar_mw        = round(sum(coalesce(solar_mw, 0), na.rm = TRUE), 1),
      total_wind_mw         = round(sum(coalesce(wind_mw, 0), na.rm = TRUE), 1),
      total_renewable_mw    = round(sum(coalesce(total_renewable_mw, 0), na.rm = TRUE), 1),
      pct_with_solar        = round(mean(!is.na(solar_mw) & solar_mw > 0, na.rm = TRUE) * 100, 1)
    ) |>
    print()
}
