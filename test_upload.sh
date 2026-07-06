#!/usr/bin/env bash
# Test manual del flujo de subida contra la instancia indicada (default :8901).
set -u
PORT="${1:-8901}"
T=$(cat "$(dirname "$0")/data/upload_token.txt")
echo "-- sin token (debe fallar):"
curl -s -X POST "http://localhost:$PORT/upload" -F "files=@/tmp/demo-doc.pdf" | head -c 100
echo; echo "-- solo cookie (debe fallar: los POST no aceptan cookie, anti-CSRF):"
curl -s -X POST "http://localhost:$PORT/upload" -b "zoe_token=$T" -F "files=@/tmp/demo-doc.pdf" | head -c 100
echo; echo "-- con token (header Bearer):"
curl -s -X POST "http://localhost:$PORT/upload" -H "Authorization: Bearer $T" \
  -F "files=@/tmp/demo-doc.pdf" -F "files=@/tmp/demo-nota.html"
echo; echo "-- inbox:"
curl -s -H "Authorization: Bearer $T" "http://localhost:$PORT/inbox"
echo
