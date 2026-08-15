#!/usr/bin/env bash
# Sync this repo to the VPS and restart the stack (web + durable worker +
# Postgres) behind the Traefik that ships with Hostinger's Docker template.
#
# The server's own /docker/verdict/.env and docker-compose.override.yml (the
# Traefik routing labels) are never overwritten — secrets live only there.
#
#   ./deploy-vps.sh
set -euo pipefail

HOST="${VERDICT_VPS_HOST:-root@187.52.118.180}"
KEY="${VERDICT_VPS_KEY:-$HOME/.ssh/id_ed25519_hostinger_vps}"
REMOTE_DIR=/docker/verdict

rsync -az --delete -e "ssh -i $KEY" \
  --exclude .git --exclude .venv --exclude .venv-dev --exclude __pycache__ \
  --exclude .pytest_cache --exclude .ruff_cache --exclude '*.egg-info' \
  --exclude .env --exclude docker-compose.override.yml \
  ./ "$HOST:$REMOTE_DIR/"

ssh -i "$KEY" "$HOST" "cd $REMOTE_DIR && docker compose up -d --build"
ssh -i "$KEY" "$HOST" "cd $REMOTE_DIR && docker compose ps"
