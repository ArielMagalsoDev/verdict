# Verdict — FastAPI edition

The original Verdict interface and product story, rebuilt as one Python application. FastAPI serves the UI and API, PostgreSQL is both the durable workflow store and the first CRM adapter, and Claude performs constrained language tasks. Deterministic Python rules own the score; a human owns every CRM write.

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:8000`. The API and worker are separate processes from the same package. Leave `ANTHROPIC_API_KEY` empty to use the deterministic demo draft; set it to exercise the real Claude drafting call.

## Important behavior

- `POST /api/v1/leads` is idempotent on `submission_id` and returns a durable job.
- The worker claims queued jobs with `FOR UPDATE SKIP LOCKED`.
- Evidence is required before a numeric score can exist.
- Claude classifies/extracts/drafts; Python rules score.
- CRM changes remain `pending` until `POST /api/v1/crm-change-sets/{id}/approve` receives the configured `X-Admin-Token`.
- Replaying approval is safe and does not create a second CRM record.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn verdict.main:app --reload
verdict-worker
```

All companies and contacts in the guided demo are fictional.
