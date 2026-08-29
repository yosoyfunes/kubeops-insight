# Helm Values Reference

This page summarizes the main Helm chart values used by KubeOps Insight.

## Core sections

### Images

- `frontend.image.repository`
- `frontend.image.tag`
- `backend.image.repository`
- `backend.image.tag`

### AI

- `llm.provider`
- `llm.cacheTtlSeconds`
- `llm.maxFindings`
- `llm.maxResources`
- `llm.maxEvents`
- `llm.maxToolsPerChat`
- `llm.maxLogTailLines`
- `llm.agent.*`
- `llm.bedrock.*`
- `llm.openaiCompatible.*`

### Metrics

- `metrics.provider`
- `metrics.metricsServer.enabled`
- `metrics.metricsServer.install`
- `metrics-server.args`

### Auth

- `auth.username`
- `auth.password`
- `auth.sessionSecret`
- `auth.cookieSecure`
- `auth.existingSecret`
- `auth.oidc.*`

### Platform

- `ingress.*`
- `rbac.*`
- `networkPolicy.enabled`
- `serviceAccount.*`
- `podSecurityContext`
- `containerSecurityContext`

### ServiceAccount

- `serviceAccount.create` controls whether the chart creates the ServiceAccount
- `serviceAccount.name` overrides the generated name
- `serviceAccount.annotations` is the main place to attach an IRSA role for Bedrock on EKS

## Auth defaults to know

- login is always required
- if `auth.password` is empty, the chart generates an initial password
- if `auth.sessionSecret` is empty, the chart generates an initial session signing secret
- `auth.cookieSecure=true` is the production-safe default

## Metrics defaults to know

- Metrics Server install is disabled by default
- the product prefers not to collide with existing cluster-wide Metrics Server installations

## AI defaults to know

- Bedrock is the default provider path
- token, cycle, log, and cost controls are part of the chart surface

See `charts/kubeops-insight/values.yaml` for the full default set.
