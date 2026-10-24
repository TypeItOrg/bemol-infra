ENV ?= staging

ifneq ($(ENV),staging)
$(error ENV must be staging)
endif

.DEFAULT_GOAL := help
.PHONY: help deploy deploy-staging backup-db

help:
	@printf '%s\n' 'make deploy: validar, respaldar y desplegar staging por Compose.' 'make backup-db: backup PostgreSQL de staging.'

deploy deploy-staging:
	bash ./scripts/deploy-staging.sh

# Disable the previous timer before switching to bemol-backup@staging.service.
backup-db:
	flock /tmp/bemol-infra-staging.lock ./scripts/backup-postgres.sh staging
