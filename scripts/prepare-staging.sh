#!/usr/bin/env bash
set -euo pipefail

scripts_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

exec 9>/tmp/bemol-infra-staging.lock
flock --timeout 300 9

python3 "$scripts_dir/render-staging-config.py"

volumes=$("$scripts_dir/compose-staging.sh" config --format json | python3 -c \
  'import json,sys; print("\n".join(v["name"] for v in json.load(sys.stdin)["volumes"].values() if v.get("external")))')
while IFS= read -r volume; do
  docker volume inspect "$volume" >/dev/null
  owners=$(docker ps --filter "volume=$volume" \
    --format '{{.ID}} {{.Label "com.docker.compose.project"}}')
  if [[ -n "$owners" ]]; then
    while read -r container project; do
      if [[ "$project" != bemol-staging ]]; then
        printf 'Volume %s is used by container %s outside bemol-staging; stop the previous stack first.\n' "$volume" "$container" >&2
        exit 1
      fi
    done <<< "$owners"
  fi
done <<< "$volumes"

printf '%s\n' '[Prepare] Configuration and existing volumes checked; ready to deploy.'
