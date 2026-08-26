# KubeOps Insight Frontend

React, TypeScript and Vite frontend for KubeOps Insight.

## Scope

- Authenticated dashboard with local login and optional OIDC redirect flow.
- Cluster overview from live Kubernetes API data.
- Namespace-filtered resource views for pods, deployments, services, events, workloads, jobs, PVCs and ingresses.
- Deterministic findings view.
- Metrics summary view that handles Metrics Server `unavailable` responses.
- AI analysis and Spanish chat UI.
- Chat metadata for provider, cache status, tools used, evidence packs and Bedrock agent metrics when available.

## Configuration

The frontend uses `VITE_API_BASE_URL` for backend API calls.

Default:

```bash
VITE_API_BASE_URL=/api/v1
```

In local development, Vite proxies `/api` to `http://localhost:8000`.

## Run Locally

```bash
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

`npm run dev` binds to `0.0.0.0`; use `http://<machine-ip>:5173` from another host on the same network.

## Build And Validate

```bash
npm run lint
npm run build
```

Preview the production build:

```bash
npm run preview
```

## Helm Runtime

In Helm installs, the frontend container serves the built static app through nginx. API calls go through `/api/v1` and are proxied to the backend service by the chart-provided nginx configuration.
