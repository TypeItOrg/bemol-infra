#!/usr/bin/env bash
set -euo pipefail

account_id="${1:-}"
if [[ ! "$account_id" =~ ^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$ ]]; then
  echo 'Usage: make platform-passkey-setup ACCOUNT_ID=<platform-account-uuid>' >&2
  exit 1
fi
if [[ ! -t 1 ]]; then
  echo 'Run from an interactive SSH terminal; do not capture the setup code in logs.' >&2
  exit 1
fi
account_id="$(printf '%s' "$account_id" | tr 'A-F' 'a-f')"

container_for() {
  local service="$1" volume="$2" containers
  containers="$(docker ps --filter label=com.docker.compose.project=bemol-staging \
    --filter "label=com.docker.compose.service=$service" --filter "volume=$volume" --format '{{.ID}}')"
  if [[ ! "$containers" =~ ^[a-f0-9]+$ ]]; then
    echo "Expected exactly one staging $service container with volume $volume." >&2
    exit 1
  fi
  printf '%s' "$containers"
}

postgres="$(container_for postgres bemol-api-postgres-data-staging)"
redis="$(container_for redis bemol-api-redis-data-staging)"
exists="$(printf "SELECT count(*) FROM platform_accounts WHERE platform_account_id = '%s' AND enabled;\n" "$account_id" \
  | docker exec -i "$postgres" sh -c 'exec psql -X -v ON_ERROR_STOP=1 -At -U "$POSTGRES_USER" -d "$DB_NAME"')"
if [[ "$exists" != '1' ]]; then
  echo 'Expected an existing, enabled platform account. No authorization issued.' >&2
  exit 1
fi

code="$(openssl rand -hex 32)"
hash="$(printf '%s' "$code" | openssl dgst -sha256 -binary | openssl base64 -A)"
result="$(docker exec "$redis" redis-cli SET "bemol:platform:setup:$account_id" "$hash" EX 900)"
if [[ "$result" != 'OK' ]]; then
  echo 'Could not issue the setup authorization.' >&2
  exit 1
fi
printf 'Account: %s\nSingle-use code, valid for 15 minutes:\n%s\n' "$account_id" "$code"
printf 'Deliver privately after verifying identity. Previous keys/sessions are replaced only after successful enrollment.\n'
