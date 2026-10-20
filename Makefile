COMPOSE := docker compose
ENV ?= staging
export VERSION REQUEST_ID

# Reject unknown environments before any recipe can mutate Docker resources.
ifneq ($(words $(ENV)),1)
$(error ENV must be staging or production)
endif
ifeq ($(filter staging production,$(ENV)),)
$(error ENV must be staging or production)
endif
ENV_FILE := .env.$(ENV)
BASE_COMPOSE_FILE := compose.yaml
ENV_COMPOSE_FILE := compose.$(ENV).yaml
COMPOSE_ARGS := --env-file $(ENV_FILE) -f $(BASE_COMPOSE_FILE) -f $(ENV_COMPOSE_FILE)
LOCK_FILE := /tmp/boero-infra-$(ENV).lock

.DEFAULT_GOAL := status

.PHONY: verify-institutional-access
verify-institutional-access:
	./scripts/verify-institutional-access.sh

.PHONY: prepare preflight bootstrap deploy-ui deploy-api rollback-ui rollback-api backup-db status logs logs-api logs-api-file logs-api-request down test

prepare:
	flock $(LOCK_FILE) ./scripts/prepare-volumes.sh $(ENV)

preflight:
	@test -f "$(ENV_FILE)" || (echo "Missing $(ENV_FILE)" >&2; exit 1)
	$(COMPOSE) $(COMPOSE_ARGS) config --quiet

bootstrap:
	flock $(LOCK_FILE) ./scripts/bootstrap.sh $(ENV)

deploy-ui:
	@test -n "$$VERSION" || (echo "VERSION is required" >&2; exit 1)
	flock $(LOCK_FILE) ./scripts/deploy-service.sh $(ENV) ui "$$VERSION"

deploy-api:
	@test -n "$$VERSION" || (echo "VERSION is required" >&2; exit 1)
	flock $(LOCK_FILE) ./scripts/deploy-service.sh $(ENV) api "$$VERSION"

rollback-ui:
	flock $(LOCK_FILE) ./scripts/rollback-service.sh $(ENV) ui

rollback-api:
	flock $(LOCK_FILE) ./scripts/rollback-service.sh $(ENV) api

backup-db:
	flock $(LOCK_FILE) ./scripts/backup-postgres.sh $(ENV)

status:
	$(COMPOSE) $(COMPOSE_ARGS) ps

logs:
	$(COMPOSE) $(COMPOSE_ARGS) logs -f --tail=200

logs-api:
	$(COMPOSE) $(COMPOSE_ARGS) logs -f --tail=200 api

logs-api-file:
	$(COMPOSE) $(COMPOSE_ARGS) exec api tail -f /app/logs/boero-api.log

logs-api-request:
	@test -n "$$REQUEST_ID" || (echo "REQUEST_ID is required" >&2; exit 1)
	$(COMPOSE) $(COMPOSE_ARGS) exec api grep -- "$$REQUEST_ID" /app/logs/boero-api.log

down:
ifeq ($(ENV),staging)
	flock $(LOCK_FILE) sh -ec 'if [ -e "$(dir $(abspath $(lastword $(MAKEFILE_LIST)))).deploy/staging/dokploy-managed" ]; then echo "Staging is managed by Dokploy; legacy command is disabled" >&2; exit 1; fi; exec $(COMPOSE) $(COMPOSE_ARGS) down --remove-orphans'
else
	$(COMPOSE) $(COMPOSE_ARGS) down --remove-orphans
endif

test:
	./tests/deploy-service.test.sh
	./tests/backup-postgres.test.sh
	./tests/legacy-dokploy-guard.test.sh
	python3 ./tests/infra-config.test.py
