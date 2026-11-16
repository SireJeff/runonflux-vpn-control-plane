# VPN control plane

**Experimental public source snapshot — not production-verified.**

This snapshot contains a FastAPI control plane, reseller dashboard, Telegram bot
source and multi-protocol container integrations. The protocol engines are upstream
software, not newly authored VPN protocols. FluxCloud is an integration target,
not an endorsement or official affiliation.

## Status and rights

- No original Git history, customer database, production secrets or deployment
  authority is intentionally included.
- `LICENSE` is preserved verbatim from the source baseline. It contains an existing
  dedication and custom wording; no new AGPL or proprietary terms are applied.
- Ownership, prior grants, contributor agreements, upstream/copy-derived source,
  notices and redistribution requirements remain unresolved. Publication is not
  legal clearance or a replacement of existing license terms.
- A new repository cannot revoke earlier rights or exposed credentials.
- `SOURCE_MANIFEST.json` records pinned source and output hashes, not legal approval.

This is not a turnkey supported release. Fresh installation, upgrade compatibility,
external-provider behavior and real protocol end-to-end operation remain unverified.
Do not deploy it using another operator's resources or treat source sanitization as
proof of security, availability, anonymity or regulatory compliance. Credential
revocation and rotation have not been established by the source-preparation checks.

## Safe local checks

```bash
cd worker_api
python -m pytest --confcutdir=tests/safety tests/safety -q -o addopts=""
```

The dedicated backend workflow requires a trusted **local** Docker daemon and
Compose v2:

```bash
bash scripts/test.sh
```

It uses a separate disposable stack, not application containers. Broad existing
formatting/test debt may fail its quality stage. Real Docker/runtime verification
was not available during candidate preparation. Do not run repository-wide pytest
or point fixtures at valuable data.

## Source layout

- `worker_api/`: API, models, migrations, tests and resource-safety helpers.
- `admin-dashboard/`: Next.js source, safe replacement help and dependency lockfile.
- `telegram_bot/`: bot source; uses a separate dependency environment.
- `integrations/`: protocol images and their individual checked-in bootstrap helpers.

Cloud/DNS/bot/payment integrations require your own explicit configuration and
review. Public frontend configuration must never contain secrets. Build each protocol
from its own directory; do not overwrite helpers from a shared base blindly.

This source snapshot is published at the repository owner's direction. Source
availability does not establish licensing clearance, credential revocation, a security
audit, production readiness, or a supported service. No production deployment or
operational access is provided by publishing this repository.
