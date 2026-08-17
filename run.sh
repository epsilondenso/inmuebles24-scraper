#!/bin/bash
python main.py discover > output_discover.txt

DISCOVER_OUTPUT=$(tail -n 1 output_discover.txt)

if [ "$DISCOVER_OUTPUT"="URL list: output\property_urls.jsonl" ]
   then
      python main.py extract
      echo "Flujo completado"
fi
