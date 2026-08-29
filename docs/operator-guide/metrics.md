# Metrics

## Runtime behavior

KubeOps Insight reads resource metrics from the Kubernetes Metrics API when Metrics Server is available.

If Metrics Server is unavailable, the backend returns:

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

KubeOps Insight uses Metrics Server for the built-in metrics path.
