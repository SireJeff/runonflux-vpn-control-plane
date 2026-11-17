# Contributing

Thanks for considering a contribution. This project is an **experimental** independent
control plane; the most valuable contributions are correctness fixes, documentation
improvements, test coverage, and honest reporting of what does not work.

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

- **Security issues** do not go in a public issue. Follow [SECURITY.md](SECURITY.md).
- **Questions and usage help** belong in [SUPPORT.md](SUPPORT.md), not the issue tracker.
- Large changes (new subsystems, schema changes, protocol additions, auth or billing
  changes) should start as an issue describing the problem and the proposed approach, so
  effort is not wasted on a design that will not be accepted.
- Never include real credentials, customer data, operator domains, or production
  configuration in a commit, test fixture, issue or screenshot. Test fixtures must be
  obviously synthetic.

## Authorised scope for contributors

This repository is a curated public snapshot. It intentionally does **not** contain the
private operational history, deployment automation, or internal runbooks of the system
it was derived from. Please do not attempt to reconstruct or request them, and do not
open pull requests that add operational credentials or infrastructure-specific values.

## Development environment

Prerequisites:

| Tool | Version | Needed for |
| --- | --- | --- |
| Python | 3.11 | Backend and tooling |
| Git | any recent | All work |
| Node.js | 20+ (see `admin-dashboard/package.json`) | Dashboard work |
| Docker + Compose v2 | recent | Disposable backend test stack only |

Backend setup:

```bash
cd worker_api
python -m venv .venv
# activate, then:
pip install -r requirements.txt
```

Dashboard setup:

```bash
cd admin-dashboard
npm ci
```

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the full workflow and
[docs/CONFIGURATION.md](docs/CONFIGURATION.md) for environment variables.

## Quality gates (required)

Every change must pass the gates that apply to what it touches. A pull request that
skips them will be sent back.

**Python changes** — from the repository root, on the files you changed:

```bash
black <files>
isort <files>
flake8 <files> --max-line-length=120
mypy <files> --no-incremental --follow-imports=skip --ignore-missing-imports --no-site-packages
```

**Backend tests** — the service-free safety suite must always be runnable without a
database or external service:

```bash
cd worker_api
python -m pytest --confcutdir=tests/safety tests/safety -q -o addopts=""
```

Do not run repository-wide `pytest` against valuable data, and do not point fixtures at
a shared database. The disposable stack is:

```bash
bash scripts/test.sh     # requires a local Docker daemon with Compose v2
```

**Dashboard changes**:

```bash
cd admin-dashboard
npm run lint
npm run type-check
npm test
npm run check:guides     # fails if content/guides/*.ts drifted from docs/platform/*.md
```

**Documentation changes**:

```bash
cd admin-dashboard && npm run check:guides
```

Reviewers additionally check that relative links resolve, fenced blocks are balanced,
Mermaid diagrams have a body, and every in-app help anchor still exists in its guide.

## Writing tests

- Write the failing test first, watch it fail for the right reason, then implement.
- Test observable behaviour, not implementation detail or document wording.
- Tests must not require production access, real credentials, or network services.
- Service-free regression tests belong in `worker_api/tests/safety/`.

## Conventions

- **Branches:** short and descriptive, e.g. `fix/bot-region-label`.
- **Commits:** imperative mood, one logical change each. Explain *why* in the body when
  the reason is not obvious from the diff.
- **Pull requests:** describe the problem, the approach, the verification you actually
  ran, and anything you deliberately did not address. Link the related issue.
- **Documentation:** update the docs in the same pull request as the behaviour change,
  and add a [CHANGELOG](CHANGELOG.md) entry under `Unreleased`.
- **Platform help guides:** `docs/platform/*.md` are the source of truth for the in-app
  help pages. Keep their heading structure and section numbering intact — the dashboard
  deep-links to heading anchors — and run `npm run sync:guides` after editing them.
- **Naming:** public-facing documentation uses the repository's public project name.
  Internal identifiers such as `FLUXVPN_*` environment variables and module names are
  legacy and remain unchanged; do not rename them without a migration plan.

## Review expectations

Reviewers will check, in roughly this order:

1. Is the change safe — no secrets, no operator data, no destructive defaults?
2. Is the behaviour actually correct, and is it covered by a test that fails without it?
3. Are the quality gates green and reported honestly?
4. Are the documentation and changelog updated?
5. Is the scope proportionate, or does it need to be split?

Be prepared to narrow a large pull request. Small, verifiable changes get merged.

## Licensing of contributions

This repository's `LICENSE` is preserved from the source baseline and its rights
position is not yet resolved (see [THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md)).
Because of that:

- Do not assume contributions are accepted under a single outbound licence.
- Significant contributions should be discussed in an issue first.
- By opening a pull request you confirm you have the right to submit the code and that
  it contains no third-party material that cannot be redistributed.
