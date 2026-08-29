# Authentication

## Authentication model

KubeOps Insight requires authentication for protected product routes.

Supported modes:

- local username/password
- optional OIDC redirect login

## Local auth configuration

Relevant settings:

- `KOI_AUTH_USERNAME`
- `KOI_AUTH_PASSWORD`
- `KOI_AUTH_SESSION_SECRET`
- `KOI_AUTH_COOKIE_SECURE`

The backend fails fast at startup when required auth secrets are missing.

## OIDC configuration

Relevant settings:

- `KOI_AUTH_OIDC_ENABLED`
- `KOI_AUTH_OIDC_ISSUER_URL`
- `KOI_AUTH_OIDC_CLIENT_ID`
- `KOI_AUTH_OIDC_CLIENT_SECRET`
- `KOI_AUTH_OIDC_REDIRECT_URI`
- `KOI_AUTH_OIDC_SCOPES`
- `KOI_AUTH_OIDC_USERNAME_CLAIM`
- `KOI_AUTH_OIDC_GROUPS_CLAIM`

## Security posture

OIDC handling is hardened to:

- validate state
- expire state after a bounded window
- reject external redirect targets
- return controlled auth errors for provider failures

## Limitation

Authentication exists today, but fine-grained app authorization remains a future step. Group claims are collected, but viewer/operator product-role enforcement is not fully implemented yet.
