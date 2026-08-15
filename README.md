# Verdict — Python/FastAPI edition

A faithful clone of [Verdict](https://verdict.arielmagalso.com) — the original TypeScript/Next.js AI
lead-qualification demo — rebuilt as one Python application. FastAPI serves the UI and the API,
PostgreSQL is the durable workflow store and the first CRM adapter, and Claude performs the
constrained language tasks (classification, extraction, drafting). Deterministic Python rules own
the score; a human owns every CRM write.

> The original app: `https://github.com/ArielMagalsoDev/verdict`. This repo:
> `https://github.com/ArielMagalsoDev/verdict-python`.

## What's different from the original

The product story, design system, and all four guided demo scenarios are ported as closely as a
different stack allows. The architecture underneath differs in one deliberate way:

- **The original** processes a lead synchronously inside its `POST /api/leads` handler — one
  blocking request, 10–20 seconds uncached.
- **This port** returns `202 Accepted` immediately and a real background worker (`verdict-worker`)
  drains a Postgres-backed job queue (`FOR UPDATE SKIP LOCKED`, retries, backoff). The demo page
  polls `GET /api/v1/leads/{id}` every 750ms and reveals pipeline stages as they land in the audit
  trail — a progressive reveal the original's request/response model can't offer.
- This port also adds an **approval-gated CRM write** (`POST /api/v1/crm-change-sets/{id}/approve`,
  admin-token gated) — the original only ever *proposes* a change set and never applies one.

Everything else — the evidence-sufficiency gate, the deterministic ICP scoring engine, identity
resolution, the seeded "mini-web" research corpus, the prompt-injection defenses, the four
responsible outcomes, the design system — is a close port.

## Run locally

```bash
cp .env.example .env
docker compose up --build
```

Open `http://localhost:8000`. The web app and the worker run as separate containers from the same
package. Leave `ANTHROPIC_API_KEY` empty and the whole demo — including all four guided
scenarios and the 60-case eval suite — runs on deterministic fallbacks that reproduce the same
labeled outcomes as the real model calls, at $0. Set a real key to exercise Claude for
classification, extraction, verification, and drafting.

## Guided demo

Visit `/demo` and pick one of four scenarios, or submit your own lead. Each scenario is
engineered to land on a different one of the four responsible outcomes:

| Scenario | Outcome |
|---|---|
| Sales-ready lead (Harborline Clinics) | `qualified`, sales_ready band, full evidence |
| Insufficient evidence (Fieldwork Group) | `insufficient_evidence` — declines to guess a score |
| Duplicate & poor-fit (Talent Bridge Recruiting) | `duplicate_or_merge_review` — matches a seeded vendor contact |
| Prompt-injection attempt (Ridgeline Field Services) | `qualified` — an embedded instruction in the researched source is ignored, flagged, and never reaches the draft |

## Important behavior

- `POST /api/v1/leads` and `POST /api/v1/scenarios/{key}` are idempotent on `submission_id` and
  return a durable job pointer (`202`), not the finished result.
- The worker claims queued jobs with `FOR UPDATE SKIP LOCKED`; failed jobs retry up to 3 times
  before `failed_permanent`, refunding reserved spend.
- Evidence is required before a numeric score can exist — below the evidence floor (default 4 of
  7 core ICP criteria), no score is ever emitted, only the specific unblocking questions.
- Claude classifies, extracts, and drafts; Python rules (`verdict/domain/rules.py`) own the
  arithmetic. Every model call has a deterministic fallback used when `ANTHROPIC_API_KEY` is unset.
- Turnstile bot-check, a per-IP hourly rate limit, and a race-safe daily spend cap all guard
  `POST /api/v1/leads` — all three are env-gated and never block local/demo mode.
- CRM changes are proposed as diffs and remain `pending` until
  `POST /api/v1/crm-change-sets/{id}/approve` receives the configured `X-Admin-Token`. Replaying an
  approval is safe and never creates a second CRM record (`applied_changes` is the idempotency
  backstop).
- Outreach draft approval (`POST /api/v1/leads/{id}/draft`) is blocked server-side, not just in the
  UI, whenever the draft has unsupported claims.

## Evaluation suite

```bash
python -m verdict.evals
```

Runs a 60-case labeled set across the same 7 categories and target counts as the original spec
(15 sales-ready / 10 needs-review / 10 nurture / 10 disqualified / 5 duplicate / 5
insufficient-evidence / 5 adversarial), grades by outcome + band + injection-leakage, and writes a
scorecard to the database for `/evals` to render — including the dev-vs-held-out split and
false-score/false-refusal counts. Works identically with or without an API key; the page labels
which mode produced the last run.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check .
uvicorn verdict.main:app --reload
verdict-worker
```

Postgres is required for the worker's `SKIP LOCKED` claim query to mean anything under real
concurrency, but the whole app — including the full test suite and the eval suite — also runs
against SQLite for fast local iteration (set `DATABASE_URL=sqlite:///./dev.db`). There is no
migrations directory; the schema is created with `Base.metadata.create_all()` on startup, so
schema changes are a "drop the volume and restart" operation, same as the original's fresh-project
posture.

## Deployments

Two live deployments, exercising both halves of the design:

| | Architecture | URL |
| --- | --- | --- |
| VPS (Docker) | web + **durable worker** + Postgres, HTTPS via Traefik | https://srv1906425.hstgr.cloud |
| Vercel | serverless, `inline_processing` runs the pipeline inside the request | https://verdict-python.vercel.app |

The VPS is the reference deployment — it's the only one that can run the polling worker this
port is built around. Redeploy with `./deploy-vps.sh` (rsync + `docker compose up -d --build`);
the server's `.env` and its Traefik routing labels in `docker-compose.override.yml` are left
untouched, so secrets never leave the box.

Cloudflare Turnstile is configured on the Vercel deployment. It is deliberately *not* set on the
VPS while it answers on the shared `*.hstgr.cloud` hostname — Turnstile refuses to issue tokens
for that suffix (error 110200), and since the bot check fails closed whenever a secret is
present, leaving it configured there would block every submission. Point a real subdomain at the
VPS, add it to the Turnstile widget, then put `TURNSTILE_SITE_KEY`/`TURNSTILE_SECRET_KEY` back in
`/docker/verdict/.env`.

## Project layout

```
verdict/
  main.py            FastAPI app: HTML pages + JSON API
  pipeline.py         Stage-for-stage pipeline orchestration
  worker.py           Durable job-queue worker
  domain/              Pure logic + Claude call sites, one module per pipeline stage
  fixtures/            The 4 demo scenarios, the 15-page seeded research corpus, the escalation-strip data
  evals/               The 60-case labeled set + grading harness
  models.py            SQLAlchemy schema (mirrors the original's reconstructed Postgres schema)
  templates/, static/   Jinja2 + vanilla CSS/JS port of the original's design system
tests/                 Unit tests (rules/identity/verify/changeset/classify), pipeline e2e
                        (fallback-mode scenario reproduction), and HTTP API tests
```

All companies and contacts in the guided demo are fictional.
