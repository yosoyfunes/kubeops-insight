# Metrics

## Runtime behavior

KubeOps Insight currently uses the Kubernetes Metrics API through Metrics Server when available.

If Metrics Server is absent or not currently serving metrics, the backend returns:

```text
status=unavailable
```

The dashboard degrades gracefully instead of failing.

## Installation modes

### Use an existing Metrics Server

### Install Metrics Server as a chart dependency

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set metrics.metricsServer.install=true
```

### Local clusters that need insecure kubelet TLS

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set metrics.metricsServer.install=true \
  --set 'metrics-server.args[0]=--kubelet-insecure-tls'
```

## Scope note

The current executable product path is Metrics Server-oriented.
