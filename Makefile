ENV ?= staging

.DEFAULT_GOAL := all
.PHONY: all deploy backup-db platform-passkey-setup

all: ;

deploy:
	bash ./scripts/deploy.sh $(ENV)

backup-db:
	./scripts/backup-postgres.sh $(ENV)

export ACCOUNT_ID
platform-passkey-setup:
	@bash ./scripts/platform-passkey-setup.sh $(ENV) "$${ACCOUNT_ID}"
