#!/usr/bin/env bash
set -euo pipefail

repo_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

exec docker compose --project-name bemol-staging \
  --env-file "$repo_dir/.env.staging" \
  --env-file "$repo_dir/build/staging/domains.env" \
  -f "$repo_dir/compose.yaml" \
  -f "$repo_dir/compose.staging.yaml" "$@"
