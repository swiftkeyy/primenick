#!/usr/bin/env bash
set -euo pipefail
umask 077
[ -f .env ] || { echo ".env is required" >&2; exit 1; }
docker compose pull postgres redis nginx prometheus grafana || true
docker compose build --pull
docker compose run --rm bot alembic upgrade head
docker compose up -d --remove-orphans
docker compose ps
