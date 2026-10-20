#!/bin/sh
set -eu

root_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
repo_dir="$test_dir/repo"
mkdir -p "$repo_dir/scripts" "$repo_dir/.deploy/staging" "$test_dir/bin" "$test_dir/other"
cp "$root_dir/Makefile" "$repo_dir/Makefile"
for script in bootstrap deploy-service rollback-service prepare-volumes backup-postgres; do
  cp "$root_dir/scripts/$script.sh" "$repo_dir/scripts/"
done

export DOCKER_TRACE="$test_dir/docker.trace"
export FLOCK_TRACE="$test_dir/flock.trace"
export TEST_MARKER="$repo_dir/.deploy/staging/dokploy-managed"
export PATH="$test_dir/bin:$PATH"
cat > "$test_dir/bin/docker" <<'DOCKER'
#!/usr/bin/env python3
import os, pathlib, sys
args = sys.argv[1:]
with open(os.environ['DOCKER_TRACE'], 'a') as trace:
    trace.write(' '.join(args) + '\n')
if args[0] == 'ps':
    print('synthetic-postgres')
elif any('pg_dump' in arg for arg in args):
    print('synthetic-dump')
elif 'pg_restore' in args:
    assert sys.stdin.read().startswith('synthetic-dump')
DOCKER
cat > "$test_dir/bin/flock" <<'FLOCK'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$FLOCK_TRACE"
shift
if [ "${MARK_AFTER_LOCK:-false}" = true ]; then
  touch "$TEST_MARKER"
fi
exec "$@"
FLOCK
chmod +x "$test_dir/bin/docker" "$test_dir/bin/flock"

expect_managed_rejection() {
  if "$@" > "$test_dir/output" 2>&1; then
    echo "Expected Dokploy guard rejection: $*" >&2
    exit 1
  fi
  grep -q 'Staging is managed by Dokploy' "$test_dir/output"
  test ! -s "$DOCKER_TRACE"
}

touch "$TEST_MARKER"
printf 'UI_VERSION=sha-original\n' > "$repo_dir/.env.staging"
for cwd in "$repo_dir" "$test_dir/other"; do
  cd "$cwd"
  for script in bootstrap deploy-service rollback-service prepare-volumes; do
    expect_managed_rejection "$repo_dir/scripts/$script.sh" staging ui "sha-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  done
  expect_managed_rejection make -f "$repo_dir/Makefile" down ENV=staging
done
test "$(cat "$repo_dir/.env.staging")" = 'UI_VERSION=sha-original'
test ! -e "$repo_dir/.deploy/staging/ui.previous"
for script in bootstrap deploy-service rollback-service prepare-volumes; do
  if "$repo_dir/scripts/$script.sh" unknown ui "sha-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" > "$test_dir/output" 2>&1; then
    exit 1
  fi
  grep -q 'Environment must be staging or production' "$test_dir/output"
done

# Simulate an older command queued on flock: the marker appears only after locking.
cd "$repo_dir"
for script in bootstrap deploy-service rollback-service prepare-volumes; do
  rm "$TEST_MARKER"
  MARK_AFTER_LOCK=true expect_managed_rejection flock "$test_dir/lock" "$repo_dir/scripts/$script.sh" staging ui "sha-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
done
rm "$TEST_MARKER"
MARK_AFTER_LOCK=true expect_managed_rejection make down ENV=staging
test -s "$FLOCK_TRACE"

for environment in production; do
  for script in bootstrap deploy-service rollback-service; do
    if "$repo_dir/scripts/$script.sh" "$environment" ui "sha-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" > "$test_dir/output" 2>&1; then
      echo "Expected legacy missing configuration failure: $script $environment" >&2
      exit 1
    fi
    grep -Eq 'Missing \.env\.|No previous version recorded' "$test_dir/output"
    test ! -s "$DOCKER_TRACE"
  done
  "$repo_dir/scripts/prepare-volumes.sh" "$environment"
  make down "ENV=$environment"
  grep -q "compose --env-file .env.$environment -f compose.yaml -f compose.$environment.yaml down --remove-orphans" "$DOCKER_TRACE"
  : > "$DOCKER_TRACE"
done

BACKUP_DIR="$test_dir/backups" "$repo_dir/scripts/backup-postgres.sh" staging
test "$(find "$test_dir/backups/staging" -name '*.dump' | wc -l)" -eq 1
grep -q 'volume=boero-api-postgres-data-staging' "$DOCKER_TRACE"
echo 'Legacy Dokploy guards passed; production and staging backups remain available'
