#!/usr/bin/env bash
# Entry point kept for the staging SSH forced command and workflows
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/deploy.sh" staging
