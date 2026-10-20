#!/bin/sh
set -eu

root_dir="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
unset BACKUP_DIR BACKUP_RETENTION_DAYS CONTAINER_COUNT FAIL_PS FAIL_DUMP FAIL_VALIDATION

mkdir -p "$test_dir/bin" "$test_dir/scripts"
cp "$root_dir/scripts/backup-postgres.sh" "$test_dir/scripts/backup-postgres.sh"
export TRACE="$test_dir/docker.trace"

cat > "$test_dir/bin/docker" <<'EOF'
#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$TRACE"

case "$1" in
  ps)
    case "${CONTAINER_COUNT:-1}" in
      0) ;;
      1) printf 'abc123\n' ;;
      2) printf 'abc123\ndef456\n' ;;
    esac
    [ "${FAIL_PS:-false}" != "true" ]
    exit
    ;;
  exec)
    [ "$2" = "-i" ]
    [ "$3" = "abc123" ]
    shift 3
    ;;
  compose)
    [ "$2" = "--env-file" ]
    [ "$3" = ".env.$EXPECTED_ENV" ]
    [ "$4" = "-f" ]
    [ "$5" = "compose.yaml" ]
    [ "$6" = "-f" ]
    [ "$7" = "compose.$EXPECTED_ENV.yaml" ]
    [ "$8" = "exec" ]
    [ "$9" = "-T" ]
    shift 9
    [ "$1" = "postgres" ]
    shift
    ;;
  *) exit 1 ;;
esac

case "$*" in
  *pg_dump*)
    printf 'synthetic custom archive\n'
    [ "${FAIL_DUMP:-false}" != "true" ]
    ;;
  'pg_restore --list')
    grep -qx 'synthetic custom archive'
    [ "${FAIL_VALIDATION:-false}" != "true" ]
    ;;
  *) exit 1 ;;
esac
EOF
chmod +x "$test_dir/bin/docker"

reset_case() {
  rm -rf "$test_dir/backups"
  rm -f "$test_dir/.env.staging" "$test_dir/.env.qa" "$test_dir/.env.production"
  mkdir -p "$test_dir/backups/$1"
  old_archive="$test_dir/backups/$1/boero-$1-20000101T000000Z.dump"
  printf 'old archive\n' > "$old_archive"
  touch -t 200001010000 "$old_archive"
  : > "$TRACE"
}

run_backup() {
  EXPECTED_ENV="$1" PATH="$test_dir/bin:$PATH" \
    sh "$test_dir/scripts/backup-postgres.sh" "$1"
}

assert_success() {
  [ ! -e "$old_archive" ]
  set -- "$test_dir/backups/$1/"*.dump
  [ "$#" -eq 1 ]
  grep -qx 'synthetic custom archive' "$1"
  [ "$(stat -c %a "$1")" = "600" ]
  [ -z "$(find "$test_dir/backups" -name '*.tmp' -print)" ]
}

assert_preserved() {
  [ -f "$old_archive" ]
  [ "$(find "$test_dir/backups" -name '*.dump' -type f | wc -l)" -eq 1 ]
  [ -z "$(find "$test_dir/backups" -name '*.tmp' -print)" ]
}

for environment in qa production; do
  reset_case "$environment"
  printf 'BACKUP_DIR=%s/backups\nBACKUP_RETENTION_DAYS=7\n' "$test_dir" > "$test_dir/.env.$environment"
  run_backup "$environment"
  assert_success "$environment"
  ! grep -q '^ps\|^exec ' "$TRACE"

  reset_case "$environment"
  if BACKUP_DIR="$test_dir/backups" run_backup "$environment"; then
    echo "Expected $environment to require its environment file" >&2
    exit 1
  fi
  [ ! -s "$TRACE" ]
  assert_preserved
done

reset_case staging
BACKUP_DIR="$test_dir/backups" run_backup staging
assert_success staging
grep -qx 'ps --filter volume=boero-api-postgres-data-staging --filter label=com.docker.compose.service=postgres --format {{.ID}}' "$TRACE"
[ "$(grep -c '^ps ' "$TRACE")" -eq 1 ]
[ "$(grep -c '^exec -i abc123 ' "$TRACE")" -eq 2 ]
! grep -q '^compose ' "$TRACE"
grep -q 'DB_NAME.*POSTGRES_USER' "$TRACE"
! grep -q 'POSTGRES_DB' "$TRACE"

reset_case staging
printf 'BACKUP_DIR=%s/unused\nBACKUP_RETENTION_DAYS=99999\n' "$test_dir" > "$test_dir/.env.staging"
BACKUP_DIR="$test_dir/backups" BACKUP_RETENTION_DAYS=7 run_backup staging
assert_success staging

reset_case staging
printf 'BACKUP_DIR=%s/backups\nBACKUP_RETENTION_DAYS=7\n' "$test_dir" > "$test_dir/.env.staging"
run_backup staging
assert_success staging

for count in 0 2; do
  reset_case staging
  if BACKUP_DIR="$test_dir/backups" CONTAINER_COUNT="$count" run_backup staging; then
    echo "Expected $count PostgreSQL containers to reject the backup" >&2
    exit 1
  fi
  ! grep -q '^exec ' "$TRACE"
  assert_preserved
done

for failure in FAIL_PS FAIL_DUMP FAIL_VALIDATION; do
  reset_case staging
  if env BACKUP_DIR="$test_dir/backups" "$failure=true" PATH="$test_dir/bin:$PATH" \
      sh "$test_dir/scripts/backup-postgres.sh" staging; then
    echo "Expected $failure to reject the backup" >&2
    exit 1
  fi
  assert_preserved
done

echo "backup-postgres tests passed"
