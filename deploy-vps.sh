#!/usr/bin/env bash
# Sync this repo to the deployment host and restart the stack (web + durable
# worker + Postgres) behind a Traefik reverse proxy.
#
# The server's own .env and docker-compose.override.yml (the Traefik routing
# labels) are never overwritten — secrets live only there, never in this repo.
#
#   VERDICT_VPS_HOST=user@host VERDICT_VPS_KEY=~/.ssh/your_key ./deploy-vps.sh
set -euo pipefail

HOST="${VERDICT_VPS_HOST:?set VERDICT_VPS_HOST, e.g. user@your-host}"
KEY="${VERDICT_VPS_KEY:?set VERDICT_VPS_KEY, e.g. ~/.ssh/id_ed25519}"
REMOTE_DIR="${VERDICT_VPS_DIR:-/docker/verdict}"

rsync -az --delete -e "ssh -i $KEY" \
  --exclude .git --exclude .venv --exclude .venv-dev --exclude __pycache__ \
  --exclude .pytest_cache --exclude .ruff_cache --exclude '*.egg-info' \
  --exclude .env --exclude docker-compose.override.yml \
  ./ "$HOST:$REMOTE_DIR/"

ssh -i "$KEY" "$HOST" "cd $REMOTE_DIR && docker compose up -d --build"
ssh -i "$KEY" "$HOST" "cd $REMOTE_DIR && docker compose ps"
