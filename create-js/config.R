## config ##

#### install packages ####

suppressWarnings(if(!require(pacman)) install.packages("pacman"))
library(pacman)
p_load("dplyr",
       "openxlsx",
       "readxl",
       "rjson",
       "jsonlite",
       "janitor",
       "gtools",
       "httr",
       "stringr",
       "readr",
       "tidyr",
       "tibble",
       "purrr")

#### set-up folders & file names ####
data_source_root <- "create-js/inputs/"

#### Netherlands data settings ####
# All data is fetched freely from public APIs — no API key or registration required.
# Primary sources:
#   CBS OData API  (Centraal Bureau voor de Statistiek)  https://opendata.cbs.nl/ODataApi/odata/
#   PDOK / CBS WFS (Publieke Dienstverlening Op de Kaart) https://service.pdok.nl/
#   KNMI           (Koninklijk Nederlands Meteorologisch Instituut)
#   ENTSO-E        (European Network of TSOs — NL bidding zone, free API key required)
CBS_BASE   <- "https://opendata.cbs.nl/ODataApi/odata/"
PDOK_BASE  <- "https://service.pdok.nl/"
KNMI_BASE  <- "https://climexp.knmi.nl/"
ENTSOE_BASE <- "https://web-api.tp.entsoe.eu/api"
# Set env var ENTSOE_API_KEY for live electricity load + price time series:
#   Sys.setenv(ENTSOE_API_KEY = "your-key-here")
# Free registration at: https://transparency.entsoe.eu

#### Utility functions ####

transform_URL <- function(URL) {
  URL %>%
    gsub(" ", "%20", .) %>%
    gsub('"', "%22", .) %>%
    gsub("\\{", "%7B", .) %>%
    gsub("\\}", "%7D", .) %>%
    gsub("\\[", "%5B", .) %>%
    gsub("\\]", "%5D", .)
}

convert_named_vectors <- function(x) {
  if (is.list(x)) {
    lapply(x, convert_named_vectors)
  } else if (!is.null(names(x))) {
    as.list(x)
  } else {
    x
  }
}

convert_to_named_list <- function(x) {
  lapply(x, function(category) {
    if (is.list(category)) category else unname(category)
  })
}
