# Security Model

KubeOps Insight is designed around a read-only operational model.

## Core principles

- use live Kubernetes reads
- keep mutating actions disabled
- require authentication
- keep secrets out of the frontend
- keep AI bounded by architecture

## What the AI layer can do

- summarize evidence
- prioritize issues
- answer questions from bounded evidence
- use curated read-only tools when supported by the provider path

## What the AI layer cannot do

- run arbitrary shell commands
- execute unrestricted `kubectl`
- mutate workloads
- bypass application auth

## Authentication posture

- protected routes require a session
- local auth is supported
- OIDC is optional
- OIDC redirects are sanitized to local paths only
- auth cookies are secure by default in production-oriented configuration

## Secrets posture

- local dev secrets belong in `backend/.env`
- cluster secrets belong in Kubernetes Secrets
- API keys must not live in ConfigMaps
- static AWS credentials are not the preferred EKS path

## Kubernetes posture

The chart already includes:

- non-root execution
- dropped Linux capabilities
- read-only root filesystem defaults
- NetworkPolicy templates
- read-only RBAC templates
