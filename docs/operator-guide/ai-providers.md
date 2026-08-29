# AI Providers

## Supported providers

Supported providers:

- Amazon Bedrock
- OpenAI-compatible Chat Completions APIs

## Amazon Bedrock

Bedrock is the default provider.

Production path on EKS:

- use IRSA
- annotate the backend ServiceAccount
- default generated ServiceAccount name: `<release-name>-kubeops-insight`
- override with `serviceAccount.name` when a fixed name is required
- grant `bedrock:InvokeModel` and `bedrock:InvokeModelWithResponseStream` on the selected model where possible
- grant only the minimum Bedrock invocation permissions required
- avoid static AWS access keys in Helm values

Helm install:

```bash
helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=bedrock \
  --set llm.bedrock.region=us-east-1 \
  --set llm.bedrock.modelId=us.anthropic.claude-haiku-4-5-20251001-v1:0 \
  --set serviceAccount.annotations.eks\.amazonaws\.com/role-arn=arn:aws:iam::123456789012:role/KubeOpsInsightBedrockIrsaRole
```

Relevant chart values:

- `serviceAccount.create`
- `serviceAccount.name`
- `serviceAccount.annotations`

## OpenAI-compatible providers

Configure:

- `llm.provider=openai-compatible`
- `llm.openaiCompatible.baseUrl`
- `llm.openaiCompatible.model`
- `llm.openaiCompatible.existingSecret`

The referenced Secret must expose key `apiKey`.

Example install:

```bash
kubectl -n kubeops-insight create secret generic kubeops-insight-openai \
  --from-literal=apiKey='replace-me'

helm upgrade --install kubeops-insight kubeops-insight/kubeops-insight \
  --namespace kubeops-insight \
  --create-namespace \
  --set llm.provider=openai-compatible \
  --set llm.openaiCompatible.baseUrl=https://api.openai.com/v1 \
  --set llm.openaiCompatible.model=gpt-4o-mini \
  --set llm.openaiCompatible.existingSecret=kubeops-insight-openai
```

## Gemini

Gemini can be used through Google's OpenAI-compatible endpoint.

Recommended model:

```text
gemini-flash-lite-latest
```

## Bounded AI controls

The product supports controls for:

- cache TTL
- max findings
- max resources
- max events
- max tools per chat
- log-tail size
- agent cycle limits
- token limits
- estimated cost limits
