# Troubleshooting

## Backend not ready

Check:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/ready
```

Common causes:

- missing `KOI_AUTH_PASSWORD`
- missing `KOI_AUTH_SESSION_SECRET`
- invalid AI provider configuration

## Frontend cannot reach backend

Verify:

- `VITE_API_BASE_URL`
- Vite proxy configuration in local dev
- frontend nginx proxy path in Helm runtime

## Metrics show unavailable

Common causes:

- Metrics Server is not installed
- Metrics API is still starting
- Metrics API is temporarily unhealthy
- cluster RBAC does not allow metrics reads

The dashboard should stay available while metrics remain unavailable.

## OIDC login fails

Check:

- issuer URL
- client ID
- client Secret
- redirect URI
- callback path `/api/v1/auth/oidc/callback`
- browser HTTPS behavior if `auth.cookieSecure=true`

## Helm rendering fails

Run:

```bash
make helm-lint
make helm-template
```

## AI provider calls fail

For Bedrock:

- verify IRSA or local AWS SDK credentials
- verify region and model ID

For OpenAI-compatible providers:

- verify base URL
- verify model name
- verify Secret contains `apiKey`
