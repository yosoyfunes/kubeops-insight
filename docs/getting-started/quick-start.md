# Quick Start

## Prerequisites

- Kubernetes cluster access
- Helm 3
- Docker for local development workflows
- A configured AI provider if you want AI analysis

## Local development

```bash
make setup
cp backend/.env.example backend/.env
make dev
```

Open:

- Frontend: `http://localhost:5173`
- Backend docs: `http://localhost:8000/docs`

## Local login

Default local username:

```text
admin
```

The password is the value configured in `backend/.env`.

## Public Helm repository

```bash
helm repo add kubeops-insight https://yosoyfunes.github.io/kubeops-insight/helm
helm repo update
```

## Install the chart

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace
```
