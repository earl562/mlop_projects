.PHONY: backend-test frontend-install frontend-lint frontend-build frontend-test-ui pair-poison-matrix repo-hygiene deploy-clean verify-local verify-local-no-browser

PLOTLOT_DIR := plotlot
FRONTEND_DIR := $(PLOTLOT_DIR)/frontend

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

pair-poison-matrix:
	python3 scripts/ci/run_poison_matrix.py .omo/evidence/task-12-repository-pair-ci/poison-matrix.json

repo-hygiene:
	python3 $(PLOTLOT_DIR)/scripts/check_repo_hygiene.py

deploy-clean:
	python3 $(PLOTLOT_DIR)/scripts/clean_deploy_artifacts.py

verify-local:
	$(MAKE) -C $(PLOTLOT_DIR) verify-local

verify-local-no-browser:
	$(MAKE) -C $(PLOTLOT_DIR) verify-local-no-browser
