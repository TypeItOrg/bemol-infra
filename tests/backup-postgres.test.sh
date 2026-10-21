#!/bin/sh
set -eu

root_dir="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
unset BACKUP_DIR BACKUP_RETENTION_DAYS CONTAINER_COUNT FAIL_PS FAIL_DUMP FAIL_VALIDATION BACKUP_POSTGRES_VOLUME

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
  rm -f "$test_dir/.env.staging"
  mkdir -p "$test_dir/backups/$1"
  old_archive="$test_dir/backups/$1/bemol-$1-20000101T000000Z.dump"
  printf 'old archive\n' > "$old_archive"
  touch -t 200001010000 "$old_archive"
  : > "$TRACE"
}

run_backup() {
  PATH="$test_dir/bin:$PATH" \
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

for environment in production qa unknown ../staging 'staging production' ''; do
  reset_case staging
  if BACKUP_DIR="$test_dir/backups" run_backup "$environment"; then
    echo "Expected an unsupported environment to be rejected" >&2
    exit 1
  fi
  [ ! -s "$TRACE" ]
  assert_preserved
done

reset_case staging
BACKUP_DIR="$test_dir/backups" run_backup staging
assert_success staging
grep -qx 'ps --filter volume=bemol-api-postgres-data-staging --filter label=com.docker.compose.service=postgres --format {{.ID}}' "$TRACE"
[ "$(grep -c '^ps ' "$TRACE")" -eq 1 ]
[ "$(grep -c '^exec -i abc123 ' "$TRACE")" -eq 2 ]
! grep -q '^compose ' "$TRACE"
grep -q 'DB_NAME.*POSTGRES_USER' "$TRACE"
! grep -q 'POSTGRES_DB' "$TRACE"

reset_case staging
BACKUP_DIR="$test_dir/backups" BACKUP_POSTGRES_VOLUME=bemol-acceptance-fixture-postgres-data run_backup staging
assert_success staging
grep -qx 'ps --filter volume=bemol-acceptance-fixture-postgres-data --filter label=com.docker.compose.service=postgres --format {{.ID}}' "$TRACE"
! grep -q 'bemol-api-postgres-data-staging' "$TRACE"

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

for retention in 0 -1 invalid; do
  reset_case staging
  if BACKUP_DIR="$test_dir/backups" BACKUP_RETENTION_DAYS="$retention" run_backup staging; then
    echo "Expected invalid retention to reject the backup" >&2
    exit 1
  fi
  [ ! -s "$TRACE" ]
  assert_preserved
done

reset_case staging
if BACKUP_DIR=relative-path run_backup staging; then
  echo "Expected a relative backup directory to be rejected" >&2
  exit 1
fi
[ ! -s "$TRACE" ]
assert_preserved

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
