#!/bin/bash

set -u
set -o pipefail

log() {
    echo "[$(date '+%F %T')] $*" | tee -a scraper.log
}

retry() {
    local max=5
    local delay=30

    for ((i=1; i<=max; i++)); do
        "$@" && return 0

        log "Intento $i/$max falló. Reintentando en ${delay}s..."
        sleep "$delay"
    done

    return 1
}

run() {
    local NAME="$1"

    local CHECKPOINT="output/checkpoint_${NAME}.json"
    local CSV="output/properties_${NAME}.csv"

    # Ya terminó completamente
    if [[ -f "$CHECKPOINT" && -f "$CSV" ]]; then
        log "$NAME ya tiene checkpoint y CSV. Saltando."
        return 0
    fi

    # Discover ya terminó antes
    if [[ -f "$CHECKPOINT" ]]; then
        log "$NAME ya tiene checkpoint. Saltando discover."

        if retry timeout 3h python main.py extract; then
            return 0
        else
            log "Extract falló."
            return 1
        fi
    fi

    # Ejecutar discover
    if ! retry timeout 45m python main.py discover > output_discover.txt; then
        log "Discover falló."
        return 1
    fi

    DISCOVER_OUTPUT=$(tail -n 1 output_discover.txt)
    if [[ "$DISCOVER_OUTPUT" == "URL list: output\urls_${NAME}.jsonl" ]]; then
        sleep 5

        if retry timeout 3h python main.py extract; then
            return 0
        else
            log "Extract falló."
            return 1
        fi
    else
        log "Discover terminó con una salida inesperada: $DISCOVER_OUTPUT"
        return 1
    fi
}

# Evita finales de línea CRLF
sed -i 's/\r$//' search_urls.txt
sed -i 's/\r$//' states_list.txt

while read -r URL && read -r NAME <&3
do
    NAME="${NAME// /}"

    log "Iniciando estado: $NAME"

    sed -i "s|^\([[:space:]]*\)base:.*|\1base: $URL|" config.yaml
    sed -i "s|^\([[:space:]]*\)urls_file:.*|\1urls_file: \"urls_${NAME}.jsonl\"|" config.yaml
    sed -i "s|^\([[:space:]]*\)details_file_csv:.*|\1details_file_csv: \"properties_${NAME}.csv\"|" config.yaml
    sed -i "s|^\([[:space:]]*\)details_file:.*|\1details_file: \"properties_${NAME}.xlsx\"|" config.yaml
    sed -i "s|^\([[:space:]]*\)checkpoint_file:.*|\1checkpoint_file: \"checkpoint_${NAME}.json\"|" config.yaml

    if run "$NAME"; then
        log "Estado $NAME completado."
    else
        log "Estado $NAME falló. Continuando con el siguiente."
        continue
    fi

    sleep $((RANDOM % 20 + 10))

done < search_urls.txt 3< states_list.txt

log "Proceso finalizado."