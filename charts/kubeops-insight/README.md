# KubeOps Insight Helm Chart

KubeOps Insight is a Helm-installed Kubernetes operations dashboard with deterministic diagnostics, read-only investigations, optional Metrics Server integration and required AI-assisted analysis through Amazon Bedrock or OpenAI-compatible providers.

Bedrock chat uses a Strands diagnostic agent. The agent chooses bounded read-only Kubernetes tools, gathers relevant evidence, and returns agent metrics such as cycles, tools executed, tokens, duration, estimated cost and finish reason. OpenAI-compatible providers use compact evidence packs to keep prompts small and provider-agnostic.

## Install

Add the Helm repository:

```bash
helm repo add kubeops-insight https://yosoyfunes.github.io/kubeops-insight
helm repo update
```

Install the chart:

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace
```

## Access

The chart installs a frontend service on port `80` and a backend service on port `8000`.

```bash
kubectl -n kubeops-insight port-forward svc/kubeops-insight-kubeops-insight-frontend 5173:80
```

Open `http://localhost:5173`.

Authentication is always required. If `auth.password` is empty, the chart generates and preserves a random password in the chart-managed Secret.

```bash
kubectl -n kubeops-insight get secret kubeops-insight-kubeops-insight-auth \
  -o jsonpath='{.data.password}' | base64 --decode
```

Default username: `admin`.

## Metrics Server

The chart can use an existing Metrics Server or install it as an optional dependency. Installation is disabled by default to avoid conflicts with clusters that already provide it.

If Metrics Server is absent, starting, unavailable or unable to serve metrics, KubeOps Insight reports metrics as `unavailable` instead of failing the dashboard.

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set metrics.metricsServer.install=true
```

For local clusters that require insecure kubelet TLS, pass dependency args explicitly.

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set metrics.metricsServer.install=true \
  --set 'metrics-server.args[0]=--kubelet-insecure-tls'
```

## Ingress

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set ingress.enabled=true \
  --set ingress.className=nginx \
  --set ingress.hosts[0].host=kubeops.example.com
```

## Amazon Bedrock

Bedrock is the default provider. For EKS production installs, use IRSA so the AWS SDK obtains temporary credentials from the annotated ServiceAccount. Static AWS access keys are not supported by this chart.

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=bedrock \
  --set llm.bedrock.region=us-east-1 \
  --set llm.bedrock.modelId=us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --set serviceAccount.annotations.eks\.amazonaws\.com/role-arn=arn:aws:iam::123456789012:role/KubeOpsInsightBedrockIrsaRole
```

For local development, run the backend outside the cluster with an AWS SSO-backed profile and set `KOI_AWS_PROFILE`. Do not mount AWS credential files into the Helm deployment.

```bash
AWS_PROFILE=claude KOI_AWS_PROFILE=claude KOI_LLM_PROVIDER=bedrock .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## OpenAI-Compatible Provider

Create a Secret with key `apiKey`.

```bash
kubectl -n kubeops-insight create secret generic kubeops-insight-openai \
  --from-literal=apiKey='replace-me'
```

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=openai-compatible \
  --set llm.openaiCompatible.baseUrl=https://api.openai.com/v1 \
  --set llm.openaiCompatible.model=gpt-4o-mini \
  --set llm.openaiCompatible.existingSecret=kubeops-insight-openai
```

### Gemini

Gemini can be used through Google's OpenAI-compatible endpoint. `gemini-flash-lite-latest` is currently recommended because `gemini-flash-latest` may return transient high-demand `503` errors.

```bash
kubectl -n kubeops-insight create secret generic kubeops-insight-gemini \
  --from-literal=apiKey='replace-me'
```

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=openai-compatible \
  --set llm.openaiCompatible.baseUrl=https://generativelanguage.googleapis.com/v1beta/openai \
  --set llm.openaiCompatible.model=gemini-flash-lite-latest \
  --set llm.openaiCompatible.existingSecret=kubeops-insight-gemini
```

## SSO/OIDC

Configure the identity provider callback URL as `/api/v1/auth/oidc/callback` on the public KubeOps Insight URL. Store the client secret in a Secret key named `oidcClientSecret`.

```yaml
auth:
  enabled: true
  oidc:
    enabled: true
    issuerUrl: https://dev-000000.okta.com/oauth2/default
    clientId: okta-client-id
    existingSecret: kubeops-insight-okta
    redirectUri: https://kubeops.example.com/api/v1/auth/oidc/callback
    scopes: "openid profile email groups"
```

## Security Defaults

- Read-only Kubernetes RBAC by default.
- Actions are disabled by default.
- No arbitrary shell execution.
- AI analysis uses bounded read-only Kubernetes API tools.
- Non-root containers and read-only root filesystem defaults.
- NetworkPolicy and PodDisruptionBudget templates are included.

## Values

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `auth.username` | string | `admin` | Local login username. |
| `auth.existingSecret` | string | `""` | Existing Secret with `password` and `sessionSecret`. |
| `auth.oidc.enabled` | bool | `false` | Enable OIDC login. |
| `ingress.enabled` | bool | `false` | Create an Ingress for the frontend. |
| `metrics.metricsServer.install` | bool | `false` | Install the optional Metrics Server dependency. |
| `metrics-server.args` | list | `[]` | Extra args passed to the optional Metrics Server dependency. |
| `llm.provider` | string | `bedrock` | `bedrock` or `openai-compatible`. |
| `llm.agent.maxCycles` | int | `5` | Maximum Strands agent reasoning cycles per request. |
| `llm.agent.timeoutSeconds` | int | `30` | Maximum wall-clock seconds per agent request. |
| `llm.agent.maxInputTokens` | int | `25000` | Maximum estimated/observed input tokens per request. |
| `llm.agent.maxOutputTokens` | int | `2000` | Maximum output tokens per request. |
| `llm.agent.logs.maxLines` | int | `200` | Maximum log lines returned by log tools. |
| `llm.agent.logs.maxCharacters` | int | `20000` | Maximum log characters returned by log tools. |
| `llm.agent.cost.maxEstimatedCostPerRequest` | number | `0.10` | Maximum estimated request cost. |
| `llm.bedrock.modelId` | string | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock model ID. |
| `llm.openaiCompatible.baseUrl` | string | `""` | OpenAI-compatible API base URL. |
| `llm.openaiCompatible.model` | string | `""` | OpenAI-compatible model name. |
| `llm.openaiCompatible.existingSecret` | string | `""` | Secret containing OpenAI-compatible API key as `apiKey`. |
| `rbac.clusterWide` | bool | `true` | Install cluster-wide read-only RBAC. |
| `networkPolicy.enabled` | bool | `true` | Render NetworkPolicy. |
| `actions.enabled` | bool | `false` | Reserved for future mutating actions. |
