#!/usr/bin/env bash
# Entry point for the production SSH forced command and workflows
exec bash "$(dirname -- "${BASH_SOURCE[0]}")/deploy.sh" production
