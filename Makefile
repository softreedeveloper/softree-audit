.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose
API := $(COMPOSE) exec -T api

.PHONY: help
help: ## Muestra esta ayuda
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: env
env: ## Crea .env a partir de .env.example si no existe
	@test -f .env || (cp .env.example .env && echo "Creado .env — reemplaza SECRET_KEY antes de usar en red")

.PHONY: up
up: env ## Levanta postgres, redis, api y web
	$(COMPOSE) up -d --build

.PHONY: down
down: ## Detiene los servicios
	$(COMPOSE) down

.PHONY: reset
reset: ## Detiene los servicios y borra los volúmenes (destruye datos locales)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Sigue los logs de todos los servicios
	$(COMPOSE) logs -f

.PHONY: ps
ps: ## Estado de los servicios
	$(COMPOSE) ps

.PHONY: migrate
migrate: ## Aplica las migraciones
	$(API) alembic upgrade head

.PHONY: downgrade
downgrade: ## Revierte una migración
	$(API) alembic downgrade -1

.PHONY: revision
revision: ## Nueva migración autogenerada: make revision m="mensaje"
	@test -n "$(m)" || (echo 'Uso: make revision m="mensaje"' && exit 1)
	$(API) alembic revision --autogenerate -m "$(m)"

.PHONY: user
user: ## Crea un usuario de forma interactiva
	$(COMPOSE) exec api softree-audit create-user

.PHONY: shell
shell: ## Shell dentro del contenedor de la API
	$(COMPOSE) exec api bash

.PHONY: test
test: ## Suite completa (unit + integration)
	$(API) pytest

.PHONY: test-unit
test-unit: ## Solo pruebas unitarias
	$(API) pytest -m unit

.PHONY: test-integration
test-integration: ## Solo pruebas de integración
	$(API) pytest -m integration

.PHONY: test-e2e
test-e2e: ## Pruebas end to end. Requiere E2E_EMAIL y E2E_PASSWORD
	@test -n "$(E2E_EMAIL)" -a -n "$(E2E_PASSWORD)" || \
		(echo 'Uso: make test-e2e E2E_EMAIL=... E2E_PASSWORD=...' && exit 1)
	cd tests/e2e && npm install && npx playwright install chromium && \
		E2E_EMAIL="$(E2E_EMAIL)" E2E_PASSWORD="$(E2E_PASSWORD)" npx playwright test

.PHONY: e2e-up
e2e-up: ## Levanta todo lo que necesitan las pruebas E2E
	$(COMPOSE) --profile testing --profile scanner up -d
	@echo "Recuerde SSRF_ALLOW_PRIVATE_NETWORKS=true en .env para auditar el test-target"

.PHONY: lint
lint: ## ruff + mypy + tsc
	$(API) ruff check .
	$(API) ruff format --check .
	$(API) mypy softree_audit
	cd apps/web && npm run check

.PHONY: fmt
fmt: ## Formatea el código
	$(API) ruff format .
	$(API) ruff check --fix .

.PHONY: openapi
openapi: ## Exporta openapi.json y regenera los tipos TypeScript
	$(API) python -m softree_audit.scripts.export_openapi > docs/api/openapi.json
	cd apps/web && npm run gen:types
