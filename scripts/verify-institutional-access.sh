#!/bin/sh
set -eu

root_dir="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
export API_REPO="${API_REPO:-$root_dir/../bemol-api}"
export UI_REPO="${UI_REPO:-$root_dir/../bemol-ui}"
exec python3 "$root_dir/scripts/verification/acceptance.py" "$@"
