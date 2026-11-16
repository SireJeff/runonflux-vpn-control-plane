# RunOnFlux VPN Control Plane

[![Platform: RunOnFlux / FluxCloud](https://img.shields.io/badge/platform-RunOnFlux%20%2F%20FluxCloud-2B61D1)](https://runonflux.com/)
[![Status: Experimental](https://img.shields.io/badge/status-experimental-orange)](#status-and-rights)
[![Backend: FastAPI](https://img.shields.io/badge/backend-FastAPI-009688)](worker_api/)
[![Dashboard: Next.js](https://img.shields.io/badge/dashboard-Next.js-000000)](admin-dashboard/)

**Experimental public source snapshot — not production-verified.**

An independent, multi-protocol VPN control plane with integration code for the
[RunOnFlux platform](https://runonflux.com/) and FluxCloud. It brings together a
FastAPI backend, a Next.js admin/reseller dashboard, Telegram bot source, and
containerized protocol integrations.

**Independent project:** this repository is not an official RunOnFlux product and
does not imply sponsorship, endorsement, partnership, or affiliation. RunOnFlux and
FluxCloud names identify the platform targeted by the integration. The protocol
engines are upstream software, not newly authored VPN protocols.

## What is included

| Component | Source | Role |
| --- | --- | --- |
| Control-plane API | [`worker_api/`](worker_api/) | API endpoints, models, migrations, background tasks, and integration services |
| Admin/reseller dashboard | [`admin-dashboard/`](admin-dashboard/) | Next.js management interface |
| Telegram bot | [`telegram_bot/`](telegram_bot/) | Bot-based account and service interactions |
| RunOnFlux / FluxCloud integration | [`services/flux/`](worker_api/app/services/flux/) | Application API requests, node discovery, authentication, and health-monitoring code |
| Protocol containers | [`integrations/`](integrations/) | Per-protocol Dockerfiles and bootstrap helpers |
| Isolated test tooling | [`scripts/test.sh`](scripts/test.sh) | Disposable backend test-stack runner with local-daemon guards |

Protocol source directories include [SSH](integrations/ssh/),
[Shadowsocks](integrations/shadowsocks/), [Outline](integrations/outline/),
[Trojan](integrations/trojan/), [V2Ray](integrations/v2ray/), and
[HTTP proxy](integrations/http-proxy/). Inclusion of source does not mean that each
protocol has passed fresh installation or end-to-end traffic verification.

## RunOnFlux / FluxCloud integration

The repository contains source for coordinating containerized applications through
FluxCloud and Flux-node APIs:

- [FluxCloud client](worker_api/app/services/flux/client.py): application deployment
  and management requests and platform authentication support.
- [Application-spec generator](scripts/dev/generate_app_spec.py): helper for preparing
  application specifications; any required key must be supplied explicitly by you.
- [Node discovery](worker_api/app/services/flux/node_discovery.py) and
  [direct-node client](worker_api/app/services/flux/node_client.py): node discovery
  and node-level API request handling.
- [Health monitoring](worker_api/app/services/flux/health_monitor.py) and
  [background tasks](worker_api/app/tasks/flux_tasks.py): platform-related monitoring
  and asynchronous coordination.
- [Domain discovery](worker_api/app/services/fdm/flux_discovery.py): Flux application
  discovery within the domain-management integration.

Conceptually, the dashboard and bot communicate with the control-plane API, which
coordinates platform API requests and protocol containers. This source snapshot is
not a verified one-click RunOnFlux deployment or an official platform app listing.
Review compatibility with the current platform before using any integration.

### Inspect the source

```bash
git clone https://github.com/SireJeff/runonflux-vpn-control-plane.git
cd runonflux-vpn-control-plane
```

Provide your own platform account, wallet authorization, container images, domains,
and explicit configuration for any deployment. Do not use another operator's
credentials or resources. This repository does not supply production secrets,
fund a wallet, register an application, or authorize platform operations merely by
being cloned. See [safe local checks](#safe-local-checks) before running tests.

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
