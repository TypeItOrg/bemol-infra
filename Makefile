ENV ?= staging

ifneq ($(ENV),staging)
$(error ENV must be staging)
endif

.DEFAULT_GOAL := help
.PHONY: help render-staging-config prepare-staging deploy-staging backup-db verify-institutional-access test

help:
	@printf '%s\n' \
	  'make prepare-staging: genera configuración y verifica volúmenes (docs/STAGING.md).' \
	  'make deploy-staging: pull y actualización de la aplicación.' \
	  'make render-staging-config: genera la configuración pública desde deploy/staging.env.' \
	  'make backup-db: backup PostgreSQL de staging.' \
	  'make test: comprobaciones de infraestructura sin desplegar.'

render-staging-config:
	python3 ./scripts/render-staging-config.py

prepare-staging:
	bash ./scripts/prepare-staging.sh

deploy-staging:
	bash ./scripts/deploy-staging.sh

# Disable the old backup timer first.
backup-db:
	flock /tmp/bemol-infra-staging.lock ./scripts/backup-postgres.sh staging

verify-institutional-access:
	./scripts/verify-institutional-access.sh

test:
	./tests/backup-postgres.test.sh
	python3 ./tests/infra-config.test.py
	python3 ./tests/acceptance-verifier.test.py
