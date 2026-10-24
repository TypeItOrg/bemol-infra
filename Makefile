ENV ?= staging

ifneq ($(ENV),staging)
$(error ENV must be staging)
endif

.DEFAULT_GOAL := all
.PHONY: all deploy deploy-staging backup-db

all: ;

deploy deploy-staging:
	bash ./scripts/deploy-staging.sh

backup-db:
	flock /tmp/bemol-infra-staging.lock ./scripts/backup-postgres.sh staging
