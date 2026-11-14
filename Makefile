ENV ?= staging

ifeq ($(filter $(ENV),staging production),)
$(error ENV must be staging or production)
endif

LOCK := /tmp/bemol-infra-$(ENV).lock

.DEFAULT_GOAL := all
.PHONY: all deploy deploy-staging deploy-production backup-db platform-passkey-setup

all: ;

deploy:
	bash ./scripts/deploy.sh $(ENV)

deploy-staging:
	bash ./scripts/deploy.sh staging

deploy-production:
	bash ./scripts/deploy.sh production

backup-db:
	flock $(LOCK) ./scripts/backup-postgres.sh $(ENV)

export ACCOUNT_ID
platform-passkey-setup:
	@flock $(LOCK) bash ./scripts/platform-passkey-setup.sh $(ENV) "$${ACCOUNT_ID}"
