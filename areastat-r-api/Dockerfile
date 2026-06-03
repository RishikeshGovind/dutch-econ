FROM rocker/r-ver:4.3.3

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libcurl4-openssl-dev \
    libssl-dev \
    libxml2-dev \
    libsodium-dev \
    zlib1g-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN R -e "install.packages(c('plumber','jsonlite','here','dplyr','tidyr'), repos='https://cloud.r-project.org/', dependencies=TRUE)" && \
    R -e "library(plumber); cat('plumber OK\n')"

RUN mkdir -p data && \
    curl -fL https://github.com/RishikeshGovind/areastat-at/raw/main/data/final_json.rds \
    -o data/final_json.rds && \
    curl -fL https://github.com/RishikeshGovind/areastat-at/raw/main/data/panel_dataset.csv \
    -o data/panel_dataset.csv

COPY plumber.R .

EXPOSE 7860

CMD ["Rscript", "-e", \
  "port <- as.integer(Sys.getenv('PORT', '7860')); \
   pr <- plumber::plumb('plumber.R'); \
   pr$run(host='0.0.0.0', port=port)"]
