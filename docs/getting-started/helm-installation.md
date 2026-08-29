# Install with Helm

## Add the repository

```bash
helm repo add kubeops-insight https://yosoyfunes.github.io/kubeops-insight/helm
helm repo update
```

## Install with defaults

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace
```

## Install with Amazon Bedrock

Bedrock is the default provider.

For EKS, use IRSA and annotate the backend ServiceAccount:

- default generated ServiceAccount name: `<release-name>-kubeops-insight`
- override with `serviceAccount.name`

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=bedrock \
  --set llm.bedrock.region=us-east-1 \
  --set llm.bedrock.modelId=us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --set serviceAccount.annotations.eks\.amazonaws\.com/role-arn=arn:aws:iam::123456789012:role/KubeOpsInsightBedrockIrsaRole
```

If you want to bind the role to an explicit ServiceAccount name:

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=bedrock \
  --set serviceAccount.create=true \
  --set serviceAccount.name=kubeops-insight \
  --set serviceAccount.annotations.eks\.amazonaws\.com/role-arn=arn:aws:iam::123456789012:role/KubeOpsInsightBedrockIrsaRole
```

## Install with an OpenAI-compatible provider

Create a Secret with key `apiKey`:

```bash
kubectl -n kubeops-insight create secret generic kubeops-insight-openai \
  --from-literal=apiKey='replace-me'
```

Install the chart:

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=openai-compatible \
  --set llm.openaiCompatible.baseUrl=https://api.openai.com/v1 \
  --set llm.openaiCompatible.model=gpt-4o-mini \
  --set llm.openaiCompatible.existingSecret=kubeops-insight-openai
```

## Install with Gemini through the OpenAI-compatible path

```bash
kubectl -n kubeops-insight create secret generic kubeops-insight-gemini \
  --from-literal=apiKey='replace-me'

helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=openai-compatible \
  --set llm.openaiCompatible.baseUrl=https://generativelanguage.googleapis.com/v1beta/openai \
  --set llm.openaiCompatible.model=gemini-flash-lite-latest \
  --set llm.openaiCompatible.existingSecret=kubeops-insight-gemini
```

## What the chart deploys

The chart renders separate frontend and backend Deployments plus:

- Services
- ConfigMap
- auth Secret or existing Secret references
- read-only RBAC templates
- NetworkPolicy
- PodDisruptionBudget
- optional Ingress
- optional Metrics Server dependency

## Access the dashboard

```bash
kubectl -n kubeops-insight port-forward svc/kubeops-insight-kubeops-insight-frontend 5173:80
```

Open `http://localhost:5173`.

## Initial credentials

Authentication is always required.

If `auth.password` is empty, the chart generates an initial password in the chart-managed Secret:

```bash
kubectl -n kubeops-insight get secret kubeops-insight-kubeops-insight-auth \
  -o jsonpath='{.data.password}' | base64 --decode
```

Default username:

```text
admin
```

## Production guidance

For production installs, review at least these values before rollout:

- `auth.password`
- `auth.sessionSecret`
- `auth.cookieSecure`
- `auth.oidc.*`
- `ingress.*`
- `serviceAccount.create`
- `serviceAccount.name`
- `serviceAccount.annotations`
- `metrics.metricsServer.install`
- `llm.provider`
- `llm.bedrock.*`
- `llm.openaiCompatible.*`
