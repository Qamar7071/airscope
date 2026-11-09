# AirScope - common tasks. Run `make help` for a list.
SHELL := /bin/bash
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
BACKEND := $(ROOT)/backend
FRONTEND := $(ROOT)/frontend
PYTHON ?= $(shell command -v python3.11 || command -v python3)
VENV := $(BACKEND)/.venv
VPY := $(VENV)/bin/python

.PHONY: help install install-backend install-frontend start dev data check-data train train-fast test test-backend test-frontend build report clean clean-models

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: install-backend install-frontend ## Install backend (venv) and frontend dependencies

install-backend:
	@test -x $(VPY) || $(PYTHON) -m venv $(VENV)
	$(VPY) -m pip install --upgrade pip
	$(VPY) -m pip install -r $(BACKEND)/requirements.txt
	-$(VPY) -m pip install -r $(BACKEND)/requirements-optional.txt

install-frontend:
	cd $(FRONTEND) && npm install --no-audit --no-fund

start: ## Build the UI and serve everything on http://127.0.0.1:8000
	@bash $(ROOT)/scripts/start.sh

dev: ## Backend on :8000 + Vite dev server on :5173 (hot reload)
	@bash $(ROOT)/scripts/start.sh dev

data: ## Regenerate the deterministic synthetic demo data (datasets/*.csv, cache/*_demo.json)
	cd $(BACKEND) && $(VPY) -m data.demo_generator

check-data: ## Verify the bundled demo data equal a fresh deterministic regeneration
	cd $(BACKEND) && $(VPY) -m data.demo_generator --check

train: ## Train all cities with the full profile (LOSO CV, calibration, OSSE) - ~1 min per city
	cd $(BACKEND) && $(VPY) -m ml.train --city all --profile full

train-fast: ## Train all cities quickly (no OSSE benchmark) - ~10 s per city
	cd $(BACKEND) && $(VPY) -m ml.train --city all --profile fast

test: test-backend test-frontend ## Run all tests

test-backend: ## Backend unit/integration tests (offline)
	cd $(BACKEND) && $(VPY) -m pytest -q

test-frontend: ## Frontend type-check and unit tests
	cd $(FRONTEND) && npm run typecheck && npm test

build: ## Production build of the web interface (frontend/dist)
	cd $(FRONTEND) && npm run build

report: ## Write docs/demo_results.md from the trained models' computed metrics
	cd $(BACKEND) && $(VPY) -m ml.report

clean-models: ## Delete trained models (they are re-trained on next start)
	find $(BACKEND)/models -mindepth 1 -maxdepth 1 -type d -exec rm -rf {} +

clean: clean-models ## Delete models, live-data cache and build output
	rm -rf $(BACKEND)/cache/live $(FRONTEND)/dist
	find $(ROOT) -name __pycache__ -type d -prune -exec rm -rf {} +
