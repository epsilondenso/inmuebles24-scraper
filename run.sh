#!/bin/bash

run() {
   python main.py discover > output_discover.txt

   DISCOVER_OUTPUT=$(tail -n 1 output_discover.txt)

   if [ "$DISCOVER_OUTPUT"="URL list: output\property_urls.jsonl" ]
      then
         python main.py extract
   fi
}
#EVITA SALTOS DE LÍNEA 
sed -i 's/\r$//' search_urls.txt
sed -i 's/\r$//' states_list.txt

while read  -r URL && read -r NAME <&3
   
   do
      NAME="${NAME// /}"
      sed -i "s|^\([[:space:]]*\)base:.*|\1base: $URL|" config.yaml
      sed -i "s|^\([[:space:]]*\)urls_file:.*|\1urls_file: \"${NAME}_urls.json\"|" config.yaml
      sed -i "s|^\([[:space:]]*\)details_file:.*|\1details_file: \"properties_${NAME}.xlsx\"|" config.yaml
      sed -i "s|^\([[:space:]]*\)checkpoint_file:.*|\1checkpoint_file: \"checkpoint_${NAME}.json\"|" config.yaml
      run 
      
done < search_urls.txt 3< states_list.txt