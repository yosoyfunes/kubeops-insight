# AI Investigation

KubeOps Insight exposes two AI-oriented surfaces:

- structured cluster analysis
- free-form chat investigation

## Design goal

The goal is faster understanding, not autonomous action.

## Structured AI analysis

`POST /api/v1/ai/analyze` collects compact live evidence and asks the configured provider for a structured diagnostic response.

The output is designed to include:

- summary
- overall severity
- prioritized issues
- missing data
- safe-to-ignore items when appropriate

## Chat investigation

`POST /api/v1/chat` supports natural-language questions. The response remains bounded by collected evidence and, for Bedrock, bounded tool execution.

## Provider behavior

- Bedrock uses a Strands diagnostic agent with tool and cost limits.
- OpenAI-compatible providers use compact evidence packs without unrestricted tool execution.

## Safety boundaries

The AI layer does not:

- run arbitrary shell commands
- grant unrestricted `kubectl`
- mutate cluster state
- invent authority it does not have

## Visible runtime metadata

The UI can expose metadata such as:

- provider name
- cache hit status
- tools used
- evidence references
- Bedrock agent metrics when available

## Operator workflow

1. review deterministic findings first
2. narrow scope if needed
3. run AI analysis or ask a focused question
4. validate the answer against evidence and resource state
