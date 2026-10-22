#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$repo_dir"

exec 9>/tmp/bemol-infra-staging.lock
flock 9

env_file=.env.staging
if [[ ! -f "$env_file" || ! -r "$env_file" ]]; then
  echo "A readable .env.staging is required" >&2
  exit 1
fi

permissions=$(stat -c '%a' "$env_file")
if (( (8#$permissions & 077) != 0 )); then
  echo ".env.staging must not be accessible by group or others; use chmod 600" >&2
  exit 1
fi

compose=(docker compose --env-file "$env_file" -f compose.yaml -f compose.staging.yaml)
"${compose[@]}" config --quiet
"${compose[@]}" pull ui api api-storage-init

# The deploy already holds the same lock as make backup-db.
./scripts/backup-postgres.sh staging

"${compose[@]}" up --detach --pull never --wait --wait-timeout 900
