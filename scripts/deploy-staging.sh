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

compose=(docker compose --project-name bemol-staging --env-file "$env_file" -f compose.yaml -f compose.staging.yaml)
"${compose[@]}" config --quiet

"${compose[@]}" pull ui api api-storage-init

for volume in \
  bemol-ui-next-cache-staging \
  bemol-api-postgres-data-staging \
  bemol-api-redis-data-staging \
  bemol-api-logs-staging \
  bemol-api-enrollment-storage-staging; do
  docker volume create "$volume" >/dev/null
done

docker network inspect bemol-network-staging >/dev/null 2>&1 ||
  docker network create bemol-network-staging >/dev/null

install -d -m 755 .deploy/maintenance
maintenance_file=$(mktemp .deploy/maintenance/.maintenance.XXXXXX)
trap 'rm -f "$maintenance_file"' EXIT
"${compose[@]}" run --rm --no-deps --pull never --entrypoint cat -T ui \
  /app/public/maintenance.html > "$maintenance_file"
test -s "$maintenance_file"
chmod 644 "$maintenance_file"
mv -f "$maintenance_file" .deploy/maintenance/maintenance.html

"${compose[@]}" up --detach --pull missing --wait --wait-timeout 900
