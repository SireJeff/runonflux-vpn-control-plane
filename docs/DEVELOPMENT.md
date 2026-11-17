# Development

How to work on this repository without a live deployment.

## Prerequisites

| Tool | Version | Required for |
| --- | --- | --- |
| Python | 3.11 | Backend and release tooling |
| Git | recent | All work |
| Node.js | 20+ (see [`package.json`](../admin-dashboard/package.json)) | Dashboard |
| Docker + Compose v2 | recent | Disposable backend test stack only |
| Bash | recent | `scripts/test.sh` and container entrypoints |

Windows note: the backend safety suite runs natively, but `scripts/test.sh` and the
container helper scripts assume a Bash environment. Use Git Bash or WSL.

## Backend

```bash
cd worker_api
python -m venv .venv
# Linux/macOS:        source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Run the service locally (needs a reachable PostgreSQL and, for scheduled work, Redis):

```bash
export DATABASE_URL='postgresql://<user>:<password>@localhost:5432/<database>'
export REDIS_URL='redis://localhost:6379/0'
export JWT_SECRET_KEY='<generated>'
export FLUXVPN_SECRET_KEY='<generated>'
export INTERNAL_API_KEY='<generated>'
uvicorn app.main:app --reload --port 8080
```

Interactive API documentation appears at `/api/docs` **only** when `DEBUG` is enabled.
Keep it off anywhere reachable from the internet.

## Dashboard

```bash
cd admin-dashboard
npm ci
npm run dev        # http://localhost:3000
```

The dashboard expects the API at `NEXT_PUBLIC_API_URL` (default `/api/v1` through the
proxy). See [CONFIGURATION.md](CONFIGURATION.md).

## Bot

The bot is a separate process with its own dependency set:

```bash
cd telegram_bot
python -m venv .venv
pip install -r requirements.txt
python -m bot.main
```

It needs `TELEGRAM_BOT_TOKEN`, `WORKER_API_URL` and `INTERNAL_API_KEY`.

## Test layers

| Layer | Command | Needs services? |
| --- | --- | --- |
| Service-free safety suite | `cd worker_api && python -m pytest --confcutdir=tests/safety tests/safety -q -o addopts=""` | No |
| Disposable full backend stack | `bash scripts/test.sh` | Local Docker daemon |
| Dashboard unit/component | `cd admin-dashboard && npm test` | No (after `npm ci`) |
| Dashboard types and lint | `npm run type-check`, `npm run lint` | No |
| End-to-end | `npm run test:e2e` | Yes — full running stack |

Always start with the service-free suite. It is the gate that must stay green in every
environment, and it is the only suite with no external dependencies.

## Quality gates

Run these before every commit. They are not optional.

**Python** (on changed files, from the repository root):

```bash
black <files>
isort <files>
flake8 <files> --max-line-length=120
mypy <files> --no-incremental --follow-imports=skip --ignore-missing-imports --no-site-packages
```

**Dashboard**:

```bash
cd admin-dashboard
npm run lint
npm run type-check
npm test
npm run check:guides
```

**Documentation**:

```bash
cd admin-dashboard && npm run check:guides
```

Beyond guide sync, keep the properties the review relies on: relative links resolve,
fenced blocks are balanced, Mermaid diagrams have a body, and every dashboard help anchor
still exists in its guide.

**Safety tests**: add a service-free regression under
[`worker_api/tests/safety/`](../worker_api/tests/safety/) for behaviour that must hold
without infrastructure.

## Conventions

- **Test-first.** Write the failing test, watch it fail for the right reason, implement.
- **Small, reviewable commits.** One logical change; imperative subject line.
- **Services own invariants.** Routers validate and delegate; tasks reuse services.
- **Money and credentials must be idempotent.** Celery retries; approval endpoints get
  double-clicked.
- **Never widen a query because the UI filtered.** Bound every reseller-scoped query by
  the authenticated principal.
- **Guides are generated.** Edit `docs/platform/*.md`, then `npm run sync:guides`. Never
  hand-edit `admin-dashboard/content/guides/*.ts`.
- **Help headings are an interface.** Renaming a section breaks in-app deep links.

## Working with the guide pipeline

```bash
cd admin-dashboard
npm run sync:guides     # regenerate content/guides/*.ts from docs/platform/*.md
npm run check:guides    # fail if they drift
```

When you add a new dashboard route, add its anchor to
[`lib/content/help-map.ts`](../admin-dashboard/lib/content/help-map.ts) and make sure the
target heading exists — otherwise the help link silently points nowhere.

## Working with environment variables

- Add the variable to [`worker_api/app/core/config.py`](../worker_api/app/core/config.py)
  with a safe default (`None` or an empty string, never a real value).
- Add a placeholder line to [`.env.example`](../.env.example) if operators must set it.
- Document it in [CONFIGURATION.md](CONFIGURATION.md).
- Anything the browser needs gets a `NEXT_PUBLIC_` prefix and **must** be safe to publish.

## Troubleshooting the development environment

| Symptom | Likely cause |
| --- | --- |
| `scripts/test.sh` refuses to run | No Docker, Compose v2 missing, or a remote/ambiguous Docker context |
| Backend import errors at startup | `pip install -r requirements.txt` not run in the active venv |
| `alembic` failure at boot | Schema drift, or a migration applied out of order — inspect before retrying |
| Dashboard calls return 404 | `NEXT_PUBLIC_API_URL` / proxy misconfigured |
| `check:guides` fails | Markdown edited without regenerating modules |
| Help link goes nowhere | Heading text changed; update the anchor in `help-map.ts` |

## What you cannot do here

- Verify live protocol behaviour — there is no end-to-end protocol test.
- Verify platform deployment against RunOnFlux — no live credentials belong in this repo.
- Reproduce a production incident — this snapshot has no operational history.