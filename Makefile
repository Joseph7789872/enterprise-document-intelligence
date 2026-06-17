# EDIP developer convenience targets. Backend tasks run via uv in ./backend.
# Usage: `make help`
.DEFAULT_GOAL := help
.PHONY: help install lint type test test-all run migrate downgrade \
        secrets bump compose-up compose-down docker-build frontend-build

BACKEND := backend
UV := uv

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Sync backend deps (uv)
	cd $(BACKEND) && $(UV) sync

lint: ## Ruff lint the backend
	cd $(BACKEND) && $(UV) run ruff check .

type: ## mypy type-check the backend
	cd $(BACKEND) && $(UV) run mypy app

test: ## Run the offline test suite (no RAGAS)
	cd $(BACKEND) && $(UV) run pytest -m "not ragas" -q

test-all: ## Run the full test suite (requires the evals extra + keys)
	cd $(BACKEND) && $(UV) run pytest -q

run: ## Run the API locally (reload)
	cd $(BACKEND) && $(UV) run uvicorn app.main:app --reload

migrate: ## Apply DB migrations
	cd $(BACKEND) && $(UV) run alembic upgrade head

downgrade: ## Roll back one migration
	cd $(BACKEND) && $(UV) run alembic downgrade -1

secrets: ## Print fresh JWT_SECRET_KEY + MASTER_KEK
	python scripts/generate_secrets.py

bump: ## Bump version: make bump PART=patch|minor|major
	python scripts/bump_version.py $(PART)

compose-up: ## Start dev infra (postgres + redis)
	docker compose up -d

compose-down: ## Stop dev infra
	docker compose down

docker-build: ## Build the backend production image
	docker build -t edip-backend:local $(BACKEND)

frontend-build: ## Build the frontend
	cd frontend && npm ci && npm run build
