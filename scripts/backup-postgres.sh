#!/bin/sh
set -eu

environment="${1:-}"

case "$environment" in
  staging) ;;
  *) echo "Environment must be staging" >&2; exit 1 ;;
esac

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo_dir"

env_file=".env.$environment"

read_env_value() {
  key="$1"
  if [ -f "$env_file" ]; then
    sed -n "s/^${key}=//p" "$env_file" | tail -n 1
  fi
}

backup_root="${BACKUP_DIR:-$(read_env_value BACKUP_DIR)}"
retention_days="${BACKUP_RETENTION_DAYS:-$(read_env_value BACKUP_RETENTION_DAYS)}"
backup_root="${backup_root:-/var/backups/bemol}"
retention_days="${retention_days:-7}"

case "$backup_root" in
  /*) ;;
  *) echo "BACKUP_DIR must be an absolute path" >&2; exit 1 ;;
esac

case "$retention_days" in
  ''|*[!0-9]*) echo "BACKUP_RETENTION_DAYS must be a positive integer" >&2; exit 1 ;;
  0) echo "BACKUP_RETENTION_DAYS must be greater than zero" >&2; exit 1 ;;
esac

# The override lets disposable acceptance fixtures use only their own volume.
postgres_volume="${BACKUP_POSTGRES_VOLUME:-bemol-api-postgres-data-staging}"
postgres_containers="$(docker ps \
  --filter "volume=$postgres_volume" \
  --filter label=com.docker.compose.service=postgres \
  --format '{{.ID}}')"
set -- $postgres_containers
if [ "$#" -ne 1 ]; then
  echo "Expected exactly one running staging PostgreSQL container; found $#" >&2
  exit 1
fi
postgres_container="$1"

backup_dir="$backup_root/$environment"
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
final_file="$backup_dir/bemol-$environment-$timestamp.dump"
temporary_file="$backup_dir/.bemol-$environment-$timestamp.dump.tmp"

umask 077
mkdir -p "$backup_dir"
trap 'rm -f "$temporary_file"' EXIT HUP INT TERM

run_postgres() {
  docker exec -i "$postgres_container" "$@"
}

run_postgres sh -c \
  'exec pg_dump --format=custom --dbname="$DB_NAME" --username="$POSTGRES_USER"' \
  > "$temporary_file"

run_postgres pg_restore --list < "$temporary_file" > /dev/null

chmod 600 "$temporary_file"
mv "$temporary_file" "$final_file"
trap - EXIT HUP INT TERM

# Retention only runs after the new archive has passed pg_restore validation.
find "$backup_dir" -type f -name "bemol-$environment-*.dump" -mtime "+$retention_days" -delete

echo "Validated PostgreSQL backup created at $final_file"
