# Security policy

## Project status first

This repository is an **experimental source snapshot**, not a supported product.

- No security audit, penetration test or dependency review has been completed.
- No dependency install, database migration, container build or live protocol traffic
  has been verified for this snapshot.
- Credential revocation for the operational system this snapshot was derived from has
  **not** been established here. Do not assume that publishing sanitised source makes
  any previously deployed secret safe.
- Do not deploy this for real users, real money or real data without an independent
  review of the code, the infrastructure and the payment/DNS integrations you enable.

Operators are responsible for their own threat model, lawful basis, and compliance
obligations.

## Supported versions

Only the current `main` snapshot is maintained. There are no back-ported security fixes
for older commits, and no release artefacts are published. Treat any older snapshot as
unsupported.

## Reporting a vulnerability

Please **do not** open a public issue for a security problem.

Use GitHub's private vulnerability reporting on this repository
(**Security → Report a vulnerability**). If that channel is unavailable, contact the
repository owner privately through their GitHub profile and ask for a private channel
before sharing details.

Please include, as far as you can:

- what is affected (component, path or endpoint),
- the impact you believe it has,
- minimal reproduction steps or a proof of concept,
- whether the issue also exists in a live deployment you can observe.

Please do **not** include live credentials, customer data, or personal data of third
parties. If a report would require them, say so and wait for instructions.

## What to expect

This is a maintainer-run project without a commercial support contract:

- Acknowledgement is attempted within a few days.
- Triage will state whether the report is accepted, needs more information, or is out
  of scope (for example, issues that only affect a deployment's own configuration).
- Fixes are released as ordinary commits to `main` and recorded in
  [CHANGELOG.md](CHANGELOG.md). No coordinated disclosure timeline or bounty is offered.

## In scope

- Authentication, authorisation and session handling in the backend
  (`worker_api/app/core/auth/`, `worker_api/app/api/v1/endpoints/`).
- Credential generation, storage and delivery paths
  (`worker_api/app/services/credentials/`, `worker_api/app/core/crypto.py`).
- Wallet, ledger and payment flows (`worker_api/app/services/billing/`,
  `worker_api/app/services/payments/`).
- Bot-facing internal interfaces and webhook handling
  (`worker_api/app/api/v1/endpoints/internal_v2.py`,
  `worker_api/app/api/v1/endpoints/reseller_bot_webhook.py`).
- Isolation of the test stack (`docker-compose.test.yml`, `scripts/test.sh`).
- Accidental disclosure of secrets, operator data or private infrastructure in this
  repository's files or history.

## Out of scope

- Vulnerabilities in upstream protocol engines, base images or dependencies. Report
  those upstream; we will still accept a pull request that pins or mitigates.
- Findings that require a real deployment's credentials, domains or customer data.
- Missing hardening that is documented as a known limitation in
  [docs/FEATURES.md](docs/FEATURES.md) or [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
- Social engineering, physical access, or denial of service against a live deployment
  you do not own.

## Handling of secrets in this repository

- `.env*` files other than `.env.example` are ignored and must never be committed.
- `.env.example` contains only empty values and local placeholders.
- The test stack uses synthetic values and mounts no host data.
- Public project configuration must never contain secrets; dashboard-exposed variables
  are visible to any browser that can load the page.
- A reported accidentally committed secret should be assumed compromised: rotation is
  the owner's responsibility and is not performed by this repository.

See [docs/SECURITY-MODEL.md](docs/SECURITY-MODEL.md) for the trust boundaries that this
policy's scope is based on.
