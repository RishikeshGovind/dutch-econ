rm(list = ls()) # nolint: undesirable_function_linter
source("create-js/config.R")
options(useFancyQuotes = FALSE)

source("create-js/fetch_netherlands_data.R")

final_json <- convert_named_vectors(final_json)

write_json(final_json, "data.json", pretty = TRUE, auto_unbox = TRUE)

if (!dir.exists("data")) dir.create("data")
saveRDS(final_json, file = "data/final_json.rds")

message("data.json and data/final_json.rds written successfully.")
