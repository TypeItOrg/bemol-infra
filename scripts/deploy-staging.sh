#!/usr/bin/env bash
set -euo pipefail

initialize=false
if (( $# == 1 )) && [[ "$1" == "--init" ]]; then
  initialize=true
elif (( $# != 0 )); then
  echo "Usage: $0 [--init]" >&2
  exit 1
fi

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

if "$initialize"; then
  volumes=(
    bemol-ui-next-cache-staging
    bemol-api-postgres-data-staging
    bemol-api-redis-data-staging
    bemol-api-logs-staging
    bemol-api-enrollment-storage-staging
  )
  existing_volumes=$(docker volume ls --format '{{.Name}}')
  existing_networks=$(docker network ls --format '{{.Name}}')
  existing_containers=$(docker ps --all --filter label=com.docker.compose.project=bemol-staging --format '{{.ID}}')

  for volume in "${volumes[@]}"; do
    if grep -Fxq -- "$volume" <<< "$existing_volumes"; then
      echo "Initialization refused: volume $volume already exists; use normal deployment or inspect the previous installation" >&2
      exit 1
    fi
  done

  if grep -Fxq bemol-network-staging <<< "$existing_networks" || [[ -n "$existing_containers" ]]; then
    echo "Initialization refused: staging network or containers already exist; inspect the previous installation" >&2
    exit 1
  fi
fi

"${compose[@]}" pull ui api api-storage-init

if "$initialize"; then
  "${compose[@]}" pull postgres redis

  for volume in "${volumes[@]}"; do
    docker volume create "$volume" >/dev/null
  done
  docker network create bemol-network-staging >/dev/null
fi

"${compose[@]}" up --detach --pull never --wait --wait-timeout 900
