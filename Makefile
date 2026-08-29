.PHONY: setup dev test lint build backend-test frontend-build docs-build docs-serve site-dist helm-deps helm-lint helm-template package-chart helm-repo-index helm-repo kind-create kind-deploy

CHART_PATH := charts/kubeops-insight
PYTHON ?= python3
DOCS_SITE_DIR ?= site-dist
HELM_REPO_DIR ?= public/helm
HELM_REPO_URL ?= https://yosoyfunes.github.io/kubeops-insight/helm

setup:
	$(PYTHON) -m venv backend/.venv
	backend/.venv/bin/python -m pip install --upgrade pip
	backend/.venv/bin/python -m pip install -e "backend[dev]"
	cd frontend && npm install

dev:
	docker compose up --build

test: backend-test

backend-test:
	cd backend && .venv/bin/python -m pytest

lint:
	cd backend && .venv/bin/ruff check app tests
	cd frontend && npm run lint

build: frontend-build
	docker build -t kubeops-insight-backend:dev backend
	docker build -t kubeops-insight-frontend:dev frontend

frontend-build:
	cd frontend && npm run build

docs-build:
	$(PYTHON) -m mkdocs build --strict

docs-serve:
	$(PYTHON) -m mkdocs serve -a 0.0.0.0:8001

site-dist:
	rm -rf $(DOCS_SITE_DIR)
	$(PYTHON) -m mkdocs build --strict --site-dir $(DOCS_SITE_DIR)
	$(MAKE) helm-repo-index HELM_REPO_DIR=$(DOCS_SITE_DIR)/helm HELM_REPO_URL=$(HELM_REPO_URL)

helm-deps:
	helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ --force-update
	helm dependency build $(CHART_PATH) --skip-refresh

helm-lint: helm-deps
	helm lint $(CHART_PATH)

helm-template: helm-deps
	helm template kubeops-insight $(CHART_PATH)

package-chart: helm-deps
	helm package $(CHART_PATH)

helm-repo-index: helm-deps
	mkdir -p $(HELM_REPO_DIR)
	helm package $(CHART_PATH) --destination $(HELM_REPO_DIR)
	helm repo index $(HELM_REPO_DIR) --url $(HELM_REPO_URL)

helm-repo: helm-lint helm-repo-index

kind-create:
	kind create cluster --name kubeops-insight

kind-deploy:
	helm upgrade --install kubeops-insight $(CHART_PATH) --namespace kubeops-insight --create-namespace
