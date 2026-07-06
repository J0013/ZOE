#!/usr/bin/env bash
# Smoke test de /modelos y /route contra el backend (default :8900)
set -u
PORT="${1:-8900}"
T=$(cat "$(dirname "$0")/data/upload_token.txt")
echo "-- /modelos (esperado 200):"
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $T" "http://localhost:$PORT/modelos"
echo "-- /route peticion simple:"
curl -s -X POST -H "Authorization: Bearer $T" "http://localhost:$PORT/route?q=pasa+esta+lista+a+mayusculas"
echo
echo "-- /route peticion profunda:"
curl -s -X POST -H "Authorization: Bearer $T" "http://localhost:$PORT/route?q=analiza+la+evolucion+de+todos+los+proyectos+de+este+trimestre+y+proponme+cambios+de+rumbo"
echo
