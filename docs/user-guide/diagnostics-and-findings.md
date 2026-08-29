# Diagnostics and Findings

Deterministic findings are the first layer of diagnosis in KubeOps Insight.

## Why findings matter

Findings are grounded in explicit rules and live cluster data. They do not depend on model interpretation.

That makes them useful for:

- fast triage
- stable alert interpretation
- AI evidence grounding
- repeatable operator workflows

## Finding shape

Each finding includes:

- `id`
- `severity`
- `resourceKind`
- `resourceName`
- `namespace`
- `summary`
- `evidence`
- `recommendation`
- `timestamp`

## Rule coverage

KubeOps Insight checks for common Kubernetes problems such as:

- pod failures
- CrashLoopBackOff patterns
- degraded deployments
- node readiness issues
- warning event signals
- pending PVCs
- probe-related failures
- unsafe image tag patterns
- missing or weak resource requests and limits

## How to use findings

Workflow:

1. start with the most severe findings
2. confirm the affected namespace and resource
3. review evidence and recent events
4. use AI investigation only after the deterministic layer is visible

## What findings do not do

Findings do not:

- mutate workloads
- acknowledge alerts
- execute remediation
- replace root-cause verification
