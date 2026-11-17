## What this changes

<!-- One or two sentences. Link the issue this addresses, if there is one. -->

Fixes #

## Why

<!-- The problem being solved. If the reason is not obvious from the diff, explain it. -->

## How

<!-- The approach, and anything a reviewer would otherwise have to reverse-engineer. -->

## Verification

State what you actually ran, not what you assume passes. Delete rows that do not apply.

| Gate | Command | Result |
| --- | --- | --- |
| Service-free safety suite | `cd worker_api && python -m pytest --confcutdir=tests/safety tests/safety -q -o addopts=""` | |
| Disposable test stack | `bash scripts/test.sh` | |
| Python formatting | `black <files>` / `isort <files>` | |
| Python lint | `flake8 <files> --max-line-length=120` | |
| Python types | `mypy <files> --no-incremental --follow-imports=skip --ignore-missing-imports --no-site-packages` | |
| Dashboard tests | `cd admin-dashboard && npm run lint && npm run type-check && npm test` | |
| Guide sync | `cd admin-dashboard && npm run check:guides` | |
| Guides and links | `cd admin-dashboard && npm run check:guides`, plus a manual review that relative links, diagrams and help anchors still resolve | |

## Safety checklist

- [ ] No credential, token, wallet key, connection string or populated `.env` file is
      included, and no test fixture contains a value that could authenticate anywhere.
- [ ] No operator domain, real contact detail, customer record or internal incident
      narrative is introduced.
- [ ] No private infrastructure, deployment automation or operational runbook material
      is copied in from outside this repository.
- [ ] Any new dashboard-exposed variable is safe to ship to a browser.
- [ ] Changes to `docs/platform/*.md` keep the heading structure intact and
      `npm run sync:guides` has been run.

## Scope

- [ ] This is one logical change and reviewable as such.
- [ ] Documentation and the `CHANGELOG.md` entry are updated.
- [ ] Anything deliberately **not** addressed is listed below.

<!-- Known gaps, follow-ups, or parts of the change you would like reviewed hardest. -->

## Licensing

- [ ] I have the right to submit this code, and it contains no third-party material
      that cannot be redistributed under this repository's unresolved rights position
      (see `THIRD_PARTY_REVIEW.md`).