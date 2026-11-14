#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
. ./scripts/lib.sh

environment="${1:-}"
require_env "$environment"
lock_env "$environment"

# One deploy at a time on the shared host: pulls and JVM starts compete for CPU and RAM
exec 8>/tmp/bemol-infra-deploy.lock
flock 8

env_file=".env.$environment"
if [[ ! -f "$env_file" || ! -r "$env_file" ]]; then
  echo "A readable $env_file is required" >&2
  exit 1
fi

permissions=$(stat -c '%a' "$env_file")
if (( (8#$permissions & 077) != 0 )); then
  echo "$env_file must not be accessible by group or others; use chmod 600" >&2
  exit 1
fi

export BEMOL_ENV="$environment"
compose=(docker compose --env-file "$env_file" -f compose.yaml -f "compose.$environment.yaml")
"${compose[@]}" config --quiet

"${compose[@]}" pull ui api

for volume in ui-next-cache api-postgres-data api-redis-data api-logs; do
  docker volume create "bemol-$volume-$environment" >/dev/null
done

network="bemol-network-$environment"
docker network inspect "$network" >/dev/null 2>&1 ||
  docker network create "$network" >/dev/null

maintenance_dir=".deploy/maintenance/$environment"
install -d -m 755 .deploy/maintenance "$maintenance_dir"
maintenance_file=$(mktemp "$maintenance_dir/.maintenance.XXXXXX")
trap 'rm -f "$maintenance_file"' EXIT
"${compose[@]}" run --rm --no-deps --pull never --entrypoint cat -T ui \
  /app/public/maintenance.html > "$maintenance_file"
test -s "$maintenance_file"
chmod 644 "$maintenance_file"
mv -f "$maintenance_file" "$maintenance_dir/maintenance.html"

# The ui healthcheck depends on the api, so --wait can abort while the api restarts
for attempt in 1 2; do
  if "${compose[@]}" up --detach --pull missing --wait --wait-timeout 900; then
    break
  fi

  if (( attempt == 2 )); then
    exit 1
  fi

  echo "Deploy wait failed, retrying once" >&2
  sleep 15
done
