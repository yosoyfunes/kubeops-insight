# Overview Dashboard

The overview surface is designed for fast triage.

## Main concepts

- **Scope posture** summarizes the selected scope.
- **Operational counters** show findings, critical issues, impacted workloads, and warnings.
- **Cluster summary cards** reflect live Kubernetes state.
- **Priority queue** surfaces the highest-value deterministic diagnostics first.

## Scope and filtering

The dashboard supports namespace scoping.

Behavior:

- changing **Scope** changes the real operational posture of the selected scope
- changing visual filters does not redefine the real scope posture
- findings lists can be filtered separately from the scope-level posture calculation

## Data sources

The overview is assembled from:

- Kubernetes API reads
- deterministic findings
- recent warning events
- optional Metrics Server summary

## Posture and visible filters

The overview separates:

- the real health posture of the selected scope
- the currently visible filtered findings list

That keeps the hero tied to the selected scope instead of the current visual filter.
