# Shared POSIX helpers; source from the repository root.

# An environment exists when its compose.<env>.yaml overlay exists.
require_env() {
  case "${1:-}" in
    ''|*/*|.*) ;;
    *) [ -f "compose.$1.yaml" ] && return 0 ;;
  esac
  echo "Unknown environment '${1:-}': expected compose.<env>.yaml" >&2
  exit 1
}

# Serializes deploy, backup and passkey setup per environment; held until exit.
lock_env() {
  exec 9>"/tmp/bemol-infra-$1.lock"
  flock 9
}

# Prints the single running container of a service, matched by project and volume.
env_container() {
  ids=$(docker ps --filter "label=com.docker.compose.project=bemol-$1" \
    --filter "label=com.docker.compose.service=$2" --filter "volume=$3" --format '{{.ID}}')
  case "$ids" in
    ''|*[!0-9a-f]*)
      echo "Expected exactly one running $1 $2 container with volume $3" >&2
      exit 1 ;;
  esac
  printf '%s' "$ids"
}
