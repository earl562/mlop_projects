.PHONY: help backend-install backend-test backend-lint backend-fmt backend-db-up backend-db-down backend-clean \
	frontend-install frontend-dev frontend-lint frontend-build frontend-test-ui frontend-test-e2e-no-db frontend-test-e2e-db

BACKEND_DIR := apps/plotlot
FRONTEND_DIR := apps/plotlot/frontend

help:
	@echo ""
	@echo "Monorepo targets:"
	@echo "  backend-install         Install backend deps (uv)"
	@echo "  backend-lint            Ruff lint (backend)"
	@echo "  backend-fmt             Ruff format (backend)"
	@echo "  backend-test            Pytest suite (backend)"
	@echo "  backend-db-up           Start db (Docker)"
	@echo "  backend-db-down         Stop db (Docker)"
	@echo "  backend-clean           Remove backend build artifacts"
	@echo ""
	@echo "  frontend-install        Install frontend deps (npm ci)"
	@echo "  frontend-dev            Run Next.js dev server"
	@echo "  frontend-lint           ESLint"
	@echo "  frontend-build          Next.js build"
	@echo "  frontend-test-ui        Vitest UI lane"
	@echo "  frontend-test-e2e-no-db Playwright (no db)"
	@echo "  frontend-test-e2e-db    Playwright (db-backed)"
	@echo ""

backend-install:
	$(MAKE) -C $(BACKEND_DIR) install

backend-lint:
	$(MAKE) -C $(BACKEND_DIR) lint

backend-fmt:
	$(MAKE) -C $(BACKEND_DIR) fmt

backend-test:
	$(MAKE) -C $(BACKEND_DIR) test

backend-db-up:
	$(MAKE) -C $(BACKEND_DIR) db-up

backend-db-down:
	$(MAKE) -C $(BACKEND_DIR) db-down

backend-clean:
	$(MAKE) -C $(BACKEND_DIR) clean

frontend-install:
	npm --prefix $(FRONTEND_DIR) ci

frontend-dev:
	npm --prefix $(FRONTEND_DIR) run dev -- --hostname 127.0.0.1 --port 3000

frontend-lint:
	npm --prefix $(FRONTEND_DIR) run lint

frontend-build:
	npm --prefix $(FRONTEND_DIR) run build

frontend-test-ui:
	npm --prefix $(FRONTEND_DIR) run test:ui

frontend-test-e2e-no-db:
	npm --prefix $(FRONTEND_DIR) run test:e2e:no-db

frontend-test-e2e-db:
	npm --prefix $(FRONTEND_DIR) run test:e2e:db
