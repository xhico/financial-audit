# Common tasks for FinancialAudit. Run `make help` to list targets.

.DEFAULT_GOAL := help
# `make <target>` uses .env.dev; `make <target> ENV=prod` uses .env.prod
ENV ?= dev
COMPOSE := docker compose --env-file .env.$(ENV)

.PHONY: help up down restart logs ps shell migrate makemigrations superuser \
        backup restore test lint version release

help: ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# --- Development ---
up: ## Build and start the stack (detached)
	$(COMPOSE) up --build -d

down: ## Stop the stack
	$(COMPOSE) down

restart: down up ## Restart the stack

logs: ## Follow web logs
	$(COMPOSE) logs -f web

ps: ## Show stack status
	$(COMPOSE) ps

shell: ## Shell into the web container
	$(COMPOSE) exec web /bin/bash

# --- Database / Django ---
migrate: ## Apply migrations
	$(COMPOSE) exec web python manage.py migrate

makemigrations: ## Create migrations
	$(COMPOSE) exec web python manage.py makemigrations

superuser: ## Create an admin user
	$(COMPOSE) exec web python manage.py createsuperuser

backup: ## Run an on-demand database backup
	COMPOSE_PROFILES=backup $(COMPOSE) exec backup \
	  sh -c 'pg_dump --clean --if-exists | gzip > /backups/$$PGDATABASE-$$(date +%Y%m%d-%H%M%S).sql.gz'

restore: ## Restore the latest backup (DESTRUCTIVE)
	COMPOSE_PROFILES=backup $(COMPOSE) exec backup \
	  sh -c 'gunzip -c /backups/$$PGDATABASE-latest.sql.gz | psql'

# --- Quality ---
test: ## Run the test suite (pytest, ephemeral dev deps, real Postgres)
	$(COMPOSE) run --rm web sh -c "pip install -q -r requirements-dev.txt && pytest"

lint: ## Run ruff (ephemeral dev deps, no db)
	$(COMPOSE) run --rm --no-deps web sh -c "pip install -q -r requirements-dev.txt && ruff check ."

# --- Release ---
version: ## Show the latest release tag
	@git describe --tags --abbrev=0 2>/dev/null || echo "no tags yet"

release: ## Tag + push a SemVer release: make release VERSION=1.2.0
	@echo "$(VERSION)" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$$' \
	  || { echo "Usage: make release VERSION=X.Y.Z"; exit 1; }
	@git diff --quiet || { echo "Working tree is dirty — commit first."; exit 1; }
	@test "$$(git rev-parse --abbrev-ref HEAD)" = "main" \
	  || { echo "Cut releases from main (on $$(git rev-parse --abbrev-ref HEAD))."; exit 1; }
	git tag -a "v$(VERSION)" -m "v$(VERSION)"
	git push origin "v$(VERSION)"
	@echo "Pushed tag v$(VERSION)."
