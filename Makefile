.PHONY: setup dev test lint build backend-test frontend-build helm-deps helm-lint helm-template package-chart helm-repo-index helm-repo kind-create kind-deploy

CHART_PATH := charts/kubeops-insight
PYTHON ?= python3
HELM_REPO_DIR ?= public
HELM_REPO_URL ?= https://yosoyfunes.github.io/kubeops-insight

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

helm-deps:
	helm repo add metrics-server https://kubernetes-sigs.github.io/metrics-server/ --force-update
	helm dependency build $(CHART_PATH) --skip-refresh

helm-lint: helm-deps
	helm lint $(CHART_PATH)

helm-template: helm-deps
	helm template kubeops-insight $(CHART_PATH)

package-chart: helm-deps
	helm package $(CHART_PATH)

helm-repo-index:
	mkdir -p $(HELM_REPO_DIR)
	helm package $(CHART_PATH) --destination $(HELM_REPO_DIR)
	helm repo index $(HELM_REPO_DIR) --url $(HELM_REPO_URL)

helm-repo: helm-lint helm-repo-index

kind-create:
	kind create cluster --name kubeops-insight

kind-deploy:
	helm upgrade --install kubeops-insight $(CHART_PATH) --namespace kubeops-insight --create-namespace
