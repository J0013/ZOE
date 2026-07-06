#!/bin/bash
# Arranca (o reinicia) el backend en :8900. Uso: bash run.sh
cd "$(dirname "$0")"
PID=$(pgrep -f "uvicorn app:app" | head -1)
[ -n "$PID" ] && kill "$PID" && sleep 1
# Solo loopback: acceso remoto = Tailscale (y su host en ZOE_ALLOWED_HOSTS),
# NUNCA exponer el puerto a la LAN con 0.0.0.0.
nohup uvicorn app:app --host 127.0.0.1 --port 8900 \
  >/tmp/uvicorn-8900.log 2>&1 &
sleep 2
curl -sf -m 5 http://localhost:8900/health && echo " <- backend arriba"
