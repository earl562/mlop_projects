.PHONY: backend-test frontend-install frontend-lint frontend-build frontend-test-ui repo-hygiene deploy-clean deploy-doctor ship-branch verify-local verify-local-no-browser

PLOTLOT_DIR := plotlot
FRONTEND_DIR := $(PLOTLOT_DIR)/frontend
ARGS ?=

backend-test:
	$(MAKE) -C $(PLOTLOT_DIR) test

frontend-install:
	cd $(FRONTEND_DIR) && npm ci

frontend-lint:
	cd $(FRONTEND_DIR) && npm run lint

frontend-build:
	cd $(FRONTEND_DIR) && npm run build

frontend-test-ui:
	cd $(FRONTEND_DIR) && npm run test:ui

repo-hygiene:
	python3 $(PLOTLOT_DIR)/scripts/check_repo_hygiene.py

deploy-clean:
	python3 $(PLOTLOT_DIR)/scripts/clean_deploy_artifacts.py

deploy-doctor:
	python3 $(PLOTLOT_DIR)/scripts/deploy_doctor.py $(ARGS)

ship-branch:
	python3 $(PLOTLOT_DIR)/scripts/ship_branch.py $(ARGS)

verify-local:
	$(MAKE) -C $(PLOTLOT_DIR) verify-local

verify-local-no-browser:
	$(MAKE) -C $(PLOTLOT_DIR) verify-local-no-browser
