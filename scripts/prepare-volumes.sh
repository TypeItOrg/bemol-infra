#!/bin/sh
set -eu

environment="${1:-}"
case "$environment" in
  staging) suffix=staging ;;
  production) suffix=prod ;;
  *) echo "Environment must be staging or production" >&2; exit 1 ;;
esac

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if [ "$environment" = "staging" ] && [ -e "$repo_dir/.deploy/staging/dokploy-managed" ]; then
  echo "Staging is managed by Dokploy; legacy command is disabled" >&2
  exit 1
fi

# Keep historical staging/prod storage names.
for name in ui-next-cache api-postgres-data api-redis-data api-logs api-enrollment-storage; do
  docker volume create "boero-$name-$suffix"
done
