# KubeOps Insight Backend

FastAPI backend for KubeOps Insight.

## Scope

- Health and readiness endpoints.
- Live Kubernetes API reads for cluster summary, namespaces, nodes, pods, deployments, services, events, PVCs, ingresses, jobs, daemonsets, statefulsets and workload summaries.
- Deterministic findings from live Kubernetes resources and recent warning events.
- Metrics Server summary with safe `unavailable` responses when metrics are absent or temporarily unavailable.
- AI analysis and chat through Amazon Bedrock or OpenAI-compatible Chat Completions APIs.
- Bedrock chat uses the Strands diagnostic agent and bounded read-only Kubernetes tools.
- OpenAI-compatible chat uses compact evidence packs to keep prompts small and provider-agnostic.
- Local username/password auth and optional OIDC login support.

## Configuration

Settings use `KOI_` environment variables. Common values:

```bash
KOI_LLM_PROVIDER=bedrock
KOI_BEDROCK_REGION=us-east-1
KOI_BEDROCK_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0
```

For OpenAI-compatible providers:

```bash
KOI_LLM_PROVIDER=openai-compatible
KOI_OPENAI_COMPATIBLE_BASE_URL=https://api.openai.com/v1
KOI_OPENAI_COMPATIBLE_MODEL=gpt-4o-mini
KOI_OPENAI_COMPATIBLE_API_KEY=replace-me
```

For Gemini through Google's OpenAI-compatible endpoint:

```bash
KOI_LLM_PROVIDER=openai-compatible
KOI_OPENAI_COMPATIBLE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
KOI_OPENAI_COMPATIBLE_MODEL=gemini-flash-lite-latest
KOI_OPENAI_COMPATIBLE_API_KEY=replace-me
```

For local Bedrock development with AWS SSO:

```bash
AWS_PROFILE=claude KOI_AWS_PROFILE=claude KOI_LLM_PROVIDER=bedrock \
  .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
```

On EKS, use IRSA and let the AWS SDK credential chain resolve credentials from the annotated ServiceAccount.

## Run Locally

From `backend/`:

1. Create a local env file from the example and set a real password and session secret.

```bash
cp .env.example .env
```

2. Start the API.

```bash
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/ready
```

OpenAPI and interactive docs:

```text
http://localhost:8000/docs
http://localhost:8000/redoc
http://localhost:8000/openapi.json
```

The docs remain available, but protected endpoints require a valid session cookie.

## Tests And Lint

From repo root:

```bash
make test
make lint
```

From `backend/`:

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check app tests
```
