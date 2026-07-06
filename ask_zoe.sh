#!/usr/bin/env bash
# Pregunta a Zoe (agente main de OpenClaw) via CLI en el contenedor.
# Uso: ./ask_zoe.sh "pregunta"
# ponytail: paga ~22s de boot del CLI; via caliente pendiente de que el gateway exponga chat por HTTP
set -euo pipefail
docker compose -f "${ZOE_COMPOSE_FILE:?define ZOE_COMPOSE_FILE (ruta al docker-compose.yml del runtime OpenClaw)}" \
  exec -T openclaw-gateway node dist/index.js agent --agent main --message "$1"
