ENV ?= staging

ifneq ($(ENV),staging)
$(error ENV must be staging)
endif

.DEFAULT_GOAL := help
.PHONY: help init deploy deploy-staging backup-db

help:
	@printf '%s\n' 'make init: instalar staging por primera vez en un destino vacío.' 'make deploy: validar y desplegar staging por Compose, sin backup.' 'make backup-db: backup manual PostgreSQL de staging.'

init:
	bash ./scripts/deploy-staging.sh --init

deploy deploy-staging:
	bash ./scripts/deploy-staging.sh

# Disable the previous timer before switching to bemol-backup@staging.service.
backup-db:
	flock /tmp/bemol-infra-staging.lock ./scripts/backup-postgres.sh staging
