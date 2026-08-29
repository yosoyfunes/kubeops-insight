# Local Development

## Setup

```bash
make setup
cp backend/.env.example backend/.env
```

## Main commands

```bash
make dev
make test
make lint
cd frontend && npm run build
make helm-lint
make helm-template
```

## Run backend directly

From `backend/`:

```bash
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run frontend directly

From `frontend/`:

```bash
npm run dev
```

`npm run dev` binds to `0.0.0.0`, so the UI can be opened from another machine on the same network when local firewall policy allows it.

## Docs workflow

Install docs tooling:

```bash
python3 -m pip install -r docs/requirements.txt
```

Build docs:

```bash
make docs-build
```

Serve docs locally:

```bash
make docs-serve
```
