# First Login

## Authentication modes

KubeOps Insight supports:

- local username/password login
- optional OIDC redirect login

Protected product routes require a valid authenticated session.

## Local login flow

1. Open the dashboard.
2. Enter the configured username.
3. Enter the configured password.
4. Submit the login form.

For local development, credentials are typically sourced from `backend/.env`.

## OIDC login flow

When OIDC is enabled, the login screen can redirect to the configured identity provider.

The OIDC implementation in the product:

- signs and validates state
- stores state in an HTTP-only cookie
- redirects only to sanitized local paths after login
- rejects invalid or expired state
- returns controlled auth errors for upstream OIDC failures

## Session behavior

Session cookies are:

- HTTP-only
- `SameSite=Lax`
- secure by default in chart/runtime config

Local development can disable the cookie `Secure` flag explicitly through config so plain HTTP localhost flows continue to work.
