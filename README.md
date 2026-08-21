# Verdict

[![CI](https://github.com/ArielMagalsoDev/verdict/actions/workflows/ci.yml/badge.svg)](https://github.com/ArielMagalsoDev/verdict/actions/workflows/ci.yml)

An AI lead-qualification system — live at **[verdict.arielmagalso.com](https://verdict.arielmagalso.com)**.

One Python application: FastAPI serves the UI and the API, PostgreSQL is the durable workflow store
and the first CRM adapter, and Claude performs the constrained language tasks (classification,
extraction, drafting).

**Stack:** Python · FastAPI · Jinja2 · SQLAlchemy · PostgreSQL · Docker Compose · Claude API

## Five-minute engineering walkthrough

The public portfolio has a focused [Verdict case study](https://verdict.arielmagalso.com/case-study)
for reviewing the system quickly:

1. Run a guided decision at `/demo` and watch the audit stages land.
2. Read the [architecture](https://verdict.arielmagalso.com/architecture) to see where model work ends and deterministic code begins.
3. Inspect the [evaluation scorecard](https://verdict.arielmagalso.com/evals), including held-out cases, false scores, false refusals, and confidence intervals.
4. Check [live operations](https://verdict.arielmagalso.com/operations) for latency, spend, stuck work, and duplicate-write prevention.
5. Open the source below and trace the pipeline, tests, worker, and domain rules.

The case study also documents the ambiguous-identity failure that shaped the evidence gate. It is
intended to show engineering judgment and ownership, not just the finished interface.

## The problem

Inbound leads arrive faster than anyone can research them, so teams reach for an LLM — and get a
system that is confidently wrong. It invents a score for a lead it knows nothing about, quotes
"facts" that appear nowhere in the source, silently merges a new contact onto an existing CRM
record, and will follow an instruction hidden in a web page it was asked to read. The failure is
never loud; it is a plausible paragraph nobody can trace back to evidence.

## The solution

Claude is used only where language is the hard part. Deterministic Python rules own the arithmetic,
and a human owns every CRM write.

- **Evidence gate before score.** Below the evidence floor (4 of 7 core ICP criteria) no number is
  ever emitted — only the specific questions that would unblock one.
- **Deterministic scoring.** `verdict/domain/rules.py` owns the points, bands, and vetoes. The model
  never picks the score.
- **Grounded facts.** Every extracted fact must appear verbatim in its source or it is rejected and
  logged.
- **Prompt-injection defense.** Instructions embedded in researched pages are detected, flagged, and
  never reach the draft.
- **Identity resolution.** A likely-but-unproven match proposes nothing rather than merging records.
- **Diffs, not writes.** CRM changes stay `pending` until an admin token approves them; approvals are
  idempotent.
- **Durable execution.** `POST /api/v1/leads` returns `202 Accepted` and a background worker drains a
  Postgres job queue (`FOR UPDATE SKIP LOCKED`, retries, backoff). The demo page polls
  `GET /api/v1/leads/{id}` every 750ms and reveals each pipeline stage as it lands in the audit trail.
- **Measured, not asserted.** A 60-case labeled eval suite grades outcome, band, and injection
  leakage, and publishes the scorecard at `/evals`.

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

## API behavior

- `POST /api/v1/leads` and `POST /api/v1/scenarios/{key}` are idempotent on `submission_id` and
  return a durable job pointer (`202`), not the finished result.
- The worker claims queued jobs with `FOR UPDATE SKIP LOCKED`; failed jobs retry up to 3 times
  before `failed_permanent`, refunding reserved spend.
- Every model call has a deterministic fallback, used whenever `ANTHROPIC_API_KEY` is unset.
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

Runs a 60-case labeled set across 7 categories
(15 sales-ready / 10 needs-review / 10 nurture / 10 disqualified / 5 duplicate / 5
insufficient-evidence / 5 adversarial), grades by outcome + band + injection-leakage, and writes a
scorecard to the database for `/evals` to render — including the dev-vs-held-out split and
false-score/false-refusal counts. Works identically with or without an API key; the page labels
which mode produced the last run.

The latest run against production (real Claude calls, real Postgres writes) scored **57/60 (95%)** —
100% on the dev set, 92% held out — at roughly $0.01 per lead. The live numbers are always the ones
published at [/evals](https://verdict.arielmagalso.com/evals).

The scorecard reports 95% Wilson confidence intervals for the overall result and every slice. This
is deliberately more honest than presenting a small category's point estimate as certainty: a 5/5
adversarial slice is encouraging evidence, not proof of perfect real-world performance. Every push
and pull request also runs lint, unit and integration tests, plus the complete deterministic eval
suite in GitHub Actions.

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
schema changes are a "drop the volume and restart" operation.

## Deployments

Production runs on a VPS: web, the durable worker, and Postgres in Docker Compose behind Traefik
with Let's Encrypt HTTPS.

Redeploy with `./deploy-vps.sh` (rsync + `docker compose up -d --build`), pointing it at your own
host:

```bash
VERDICT_VPS_HOST=user@your-host VERDICT_VPS_KEY=~/.ssh/id_ed25519 ./deploy-vps.sh
```

The server's `.env` and its Traefik routing labels in `docker-compose.override.yml` are left
untouched, so secrets live only on the box and are never committed to this repo.

Cloudflare Turnstile guards the public lead form, with the production domain registered on the
widget. The bot check fails closed, so submissions only work on that domain.

## Project layout

```
verdict/
  main.py              FastAPI app: HTML pages + JSON API
  pipeline.py          Stage-for-stage pipeline orchestration
  worker.py            Durable job-queue worker
  models.py            SQLAlchemy schema
  domain/              Pure logic + Claude call sites, one module per pipeline stage
  fixtures/            Demo scenarios, the seeded 15-page research corpus, project data
  evals/               The 60-case labeled set + grading harness
  templates/, static/  Jinja2 templates + vanilla CSS/JS design system
tests/                 Unit tests (rules, identity, verify, changeset, classify),
                       pipeline end-to-end, and HTTP API tests
```

All companies and contacts in the guided demo are fictional.
