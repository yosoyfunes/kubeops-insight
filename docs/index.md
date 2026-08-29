# KubeOps Insight

KubeOps Insight is a Helm-installed Kubernetes operations dashboard built for live cluster visibility, deterministic diagnostics, and bounded AI-assisted investigation.

KubeOps Insight is an open source project created and maintained by Matias Anoniz.

Core product rules:

- Kubernetes reads are live and read-only.
- Authentication is required for protected product surfaces.
- AI can investigate and summarize, but it cannot run arbitrary shell commands or mutate cluster state.
- Optional dependencies such as Metrics Server degrade safely instead of breaking the dashboard.

## What the product does

KubeOps Insight combines four core capabilities:

1. Live cluster visibility from the Kubernetes API.
2. Deterministic findings for common failure patterns.
3. Namespace-scoped operational investigation.
4. Bounded AI analysis grounded in collected evidence.

## Primary workflows

Operators typically use the product in this order:

1. Sign in with local credentials or OIDC.
2. Review the current cluster or namespace posture.
3. Open deterministic findings and recent events.
4. Narrow the scope to a namespace when triage requires focus.
5. Run AI analysis or ask a natural-language question.
6. Use the evidence and next steps to continue remediation outside the product.

## Product boundaries

KubeOps Insight is not a full APM platform and it is not an autonomous remediation agent.

Product boundaries:

- no mutating Kubernetes actions
- no arbitrary shell execution
- no unrestricted `kubectl` execution through AI
- no long-term historical observability stack
- no Prometheus-first metrics mode as the current default runtime path

## Documentation map

- Use **Getting Started** for installation and first use.
- Use **User Guide** for the dashboard and AI experience.
- Use **Operator Guide** for auth, providers, metrics, and day-2 troubleshooting.
- Use **Reference** for API, Helm values, and environment variables.
- Use **Developer Guide** for local development and validation.
