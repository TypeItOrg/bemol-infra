ENV ?= staging

ifneq ($(ENV),staging)
$(error ENV must be staging)
endif

.DEFAULT_GOAL := help
.PHONY: help backup-db verify-institutional-access test

help:
	@printf '%s\n' 'Deploy, variables, estado y logs: usar Dokploy (docs/DOKPLOY-STAGING.md).' 'make backup-db: backup PostgreSQL de staging.' 'make test: comprobaciones de infraestructura sin desplegar.'

# Keep the existing command and lock used by boero-backup@staging.service.
backup-db:
	flock /tmp/boero-infra-staging.lock ./scripts/backup-postgres.sh staging

verify-institutional-access:
	./scripts/verify-institutional-access.sh

test:
	./tests/backup-postgres.test.sh
	python3 ./tests/infra-config.test.py
	python3 ./tests/acceptance-verifier.test.py
