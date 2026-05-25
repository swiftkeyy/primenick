#!/usr/bin/env bash
set -euo pipefail
TS=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p backups
source .env
 docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom --compress=9 > "backups/rarehandle_$TS.dump"
sha256sum "backups/rarehandle_$TS.dump" > "backups/rarehandle_$TS.dump.sha256"
find backups -type f -mtime +14 -delete
