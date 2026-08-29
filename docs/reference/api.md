# API Reference

## Canonical base path

Use `/api/v1` as the canonical API prefix.

The backend also mounts routes at root for compatibility, but product documentation should treat `/api/v1` as the stable public path.

## Interactive API docs

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

Protected endpoints require a valid authenticated session cookie.

## Main endpoint groups

### System

- `GET /api/v1/health`
- `GET /api/v1/ready`

### Authentication

- `GET /api/v1/auth/me`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/oidc/login`
- `GET /api/v1/auth/oidc/callback`

### Kubernetes resources

- `GET /api/v1/cluster/summary`
- `GET /api/v1/namespaces`
- `GET /api/v1/namespaces/{namespace}/summary`
- `GET /api/v1/nodes`
- `GET /api/v1/pods`
- `GET /api/v1/pods/{namespace}/{name}`
- `GET /api/v1/deployments`
- `GET /api/v1/statefulsets`
- `GET /api/v1/daemonsets`
- `GET /api/v1/jobs`
- `GET /api/v1/services`
- `GET /api/v1/pvcs`
- `GET /api/v1/ingresses`
- `GET /api/v1/events`
- `GET /api/v1/workloads`

### Diagnostics

- `GET /api/v1/findings`

### Metrics

- `GET /api/v1/metrics/summary`

### AI

- `GET /api/v1/ai/status`
- `POST /api/v1/ai/analyze`
- `POST /api/v1/chat`

## Query behavior highlights

- many resource endpoints accept optional `namespace`
- `/api/v1/events` also supports `limit` and `minutes`
- AI endpoints can operate on the selected namespace scope

## Recommendation

Use the generated OpenAPI output as the authoritative contract for request parameters and request body schemas.
