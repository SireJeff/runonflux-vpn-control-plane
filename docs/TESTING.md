# Testing

Testing in this repository is layered by what it is allowed to touch. The most important
rule is simple: **the safety layer must always run without a database, a network service,
or a container runtime.**

## Layers

| Layer | Location | Scale | Requires |
| --- | --- | --- | --- |
| Safety | [`worker_api/tests/safety/`](../worker_api/tests/safety/) | Small, curated | Nothing but Python |
| Unit | [`worker_api/tests/unit/`](../worker_api/tests/unit/) | Large (187 files) | Installed dependencies; a running database/Redis for some |
| Integration | [`worker_api/tests/integration/`](../worker_api/tests/integration/) | 31 files | PostgreSQL and Redis — use the disposable stack |
| End to end | [`worker_api/tests/e2e/`](../worker_api/tests/e2e/) | 1 file | A full running stack |
| Dashboard unit | [`admin-dashboard/`](../admin-dashboard/) (`*.test.ts(x)`) | Moderate | `npm ci` |
| Dashboard end to end | Playwright configuration | Small | A running dashboard and API |

Factories for test data live in [`worker_api/tests/factories/`](../worker_api/tests/factories/).

## Running tests

**Safety suite — run this first, always:**

```bash
cd worker_api
python -m pytest --confcutdir=tests/safety tests/safety -q -o addopts=""
```

`--confcutdir` deliberately prevents the repository's broader pytest configuration from
being pulled in, and `-o addopts=""` drops coverage flags so the run stays fast and free
of external requirements.

**Broad backend suite against disposable services:**

```bash
bash scripts/test.sh
```

This refuses to run unless a **local** Docker endpoint is available, and it will not
start the application stack. See below.

**Dashboard:**

```bash
cd admin-dashboard
npm ci
npm test              # Vitest
npm run type-check
npm run lint
npm run check:guides
```

## Isolation rules

These exist because a test suite that can reach valuable data is a liability.

- **The disposable stack is disposable.** [`docker-compose.test.yml`](../docker-compose.test.yml)
  uses a private `test-only` network, no published ports and no host volumes; PostgreSQL
  and Redis data live in `tmpfs` and vanish with the run.
- **Remote Docker is refused.** [`scripts/test.sh`](../scripts/test.sh) inspects the Docker
  endpoint and aborts on a remote or ambiguous context, so a stray `DOCKER_HOST` cannot
  point a destructive test at a real server.
- **No application environment files.** The test stack supplies synthetic values
  explicitly; it does not inherit your `.env`.
- **Prefer the service-free layer.** When a behaviour can be tested without a database,
  it belongs in `tests/safety/`, not in an integration test that needs infrastructure.
- **Fixtures must be synthetic.** Never point a fixture at real accounts, real domains,
  or a live gateway. Use reserved example domains and obviously fake identifiers.

## What is covered

- Safety: hermetic resource and fixture guards, test-runner isolation, and the guide-sync
  and documentation-integrity properties that must hold without infrastructure.
- Unit: service and helper behaviour across billing, credentials, subscriptions, free
  config, routing, bot flows and DNS automation — subject to the dependency install.
- Dashboard unit: API client wrappers, help-map/TOC parsing, formatting and conversions.

## What is not covered

| Gap | Consequence |
| --- | --- |
| No protocol end-to-end test | Nothing proves a generated credential connects |
| No migration rehearsal on a fresh database | Schema ordering is unverified here |
| No live platform test | RunOnFlux integration paths are unproven |
| No payment gateway sandbox test | Gateways are unverified in this snapshot |
| No load, soak or chaos testing | Performance and failure behaviour unknown |
| No container hardening test | Runtime hardening is not provided |

Do not read a green suite as "production ready". See
[DEPLOYMENT.md](DEPLOYMENT.md).

## Writing tests here

1. Write the test first and watch it fail for the right reason.
2. Assert observable behaviour, not internal structure or document wording.
3. Keep the safety layer dependency-free; if it needs infrastructure, it belongs in
   `tests/integration/`.
4. Never assert on secrets, real identifiers, or operator data — and never print a
   captured value in a failure message.
5. Mark infrastructure-dependent tests with the appropriate pytest marker
   (`database`, `redis`, `external`, `payment`, `celery`) so they can be excluded.

## Markers

`pytest.ini` defines markers, including `unit`, `integration`, `e2e`, `slow`,
`database`, `redis`, `external`, `payment`, `celery` and `smoke`. Unknown markers fail the
run, so use an existing one or add it deliberately.

Example: run only tests that need no infrastructure:

```bash
cd worker_api
python -m pytest -m "not database and not redis and not external and not payment" -q
```

## Related documents

- [DEVELOPMENT.md](DEVELOPMENT.md) — environment setup and quality gates
- [CONTRIBUTING.md](../CONTRIBUTING.md) — what a reviewable change includes
- [SECURITY-MODEL.md](SECURITY-MODEL.md) — why fixtures must stay synthetic