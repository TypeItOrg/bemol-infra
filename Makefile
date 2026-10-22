ENV ?= staging

ifneq ($(ENV),staging)
$(error ENV must be staging)
endif

.DEFAULT_GOAL := help
.PHONY: help deploy deploy-staging backup-db verify-institutional-access test

help:
	@printf '%s\n' 'make deploy: validar, respaldar y desplegar staging por Compose.' 'make backup-db: backup PostgreSQL de staging.' 'make test: comprobaciones de infraestructura sin desplegar.'

deploy deploy-staging:
	bash ./scripts/deploy-staging.sh

# Disable the previous timer before switching to bemol-backup@staging.service.
backup-db:
	flock /tmp/bemol-infra-staging.lock ./scripts/backup-postgres.sh staging

verify-institutional-access:
	./scripts/verify-institutional-access.sh

test:
	./tests/backup-postgres.test.sh
	python3 ./tests/infra-config.test.py
	python3 ./tests/acceptance-verifier.test.py
