#!/bin/bash
# Smoke test del backend: falla (exit != 0) si algo se rompe. Limpia su nota al final.
# Requiere el backend arrancado (bash run.sh) y funciona sin runtime OpenClaw:
# la indexacion se hace con examples/build_demo_index.py.
set -e
B="${1:-http://localhost:8900}"
MEMDIR="${ZOE_MEMORY_DIR:-./memory}"
T=$(cat "$(dirname "$0")/data/upload_token.txt")

echo "== /health =="
curl -sf -m 5 "$B/health"; echo

echo "== /ingest nota de prueba =="
RESP=$(curl -sf -m 5 -X POST "$B/ingest" -H "Authorization: Bearer $T" \
  -H "Content-Type: application/json" \
  -d '{"text":"prueba de latencia: la palabra magica es zeppelin","title":"smoke-latencia"}')
echo "$RESP"
FILE=$(echo "$RESP" | python3 -c 'import json,sys; print(json.load(sys.stdin)["stored_as"])')

echo "== reindexa (indexador demo) y busca 'zeppelin' =="
python3 "$(dirname "$0")/examples/build_demo_index.py"
OUT=$(curl -sf -m 5 -H "Authorization: Bearer $T" "$B/search?q=zeppelin")
echo "$OUT"
echo "$OUT" | grep -q "$FILE" || { echo "FALLO: la nota ingerida no aparece en /search"; exit 1; }

# Limpieza: borra la nota de prueba y reindexa para purgarla del indice.
rm -f "$MEMDIR/$FILE"
python3 "$(dirname "$0")/examples/build_demo_index.py" >/dev/null
echo "SMOKE OK"
