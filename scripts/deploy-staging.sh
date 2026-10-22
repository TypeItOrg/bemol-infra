#!/usr/bin/env bash
set -euo pipefail

scripts_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

exec 9>/tmp/bemol-infra-staging.lock
flock --timeout 300 9

"$scripts_dir/compose-staging.sh" pull
"$scripts_dir/compose-staging.sh" up -d --no-build --pull never --wait --wait-timeout 600
