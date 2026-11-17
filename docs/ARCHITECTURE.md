# Architecture overview

This is the map. Detail lives in the linked documents; each one is self-contained so you
can read only the part you need.

## System context

The control plane sits between three kinds of human actor, two delivery surfaces, and
the infrastructure that actually carries traffic.

```mermaid
flowchart TB
  subgraph People
    EU["End user"]
    RS["Reseller"]
    SA["Super admin"]
  end

  subgraph Surfaces
    PORTAL["User portal<br/>/user/*"]
    DASH["Operator dashboard<br/>/super/* , /dashboard/*"]
    BOTS["Telegram bots<br/>platform bot + reseller bots"]
  end

  CP["Control plane<br/>FastAPI + workers"]

  subgraph Platform
    FLUX["RunOnFlux / FluxCloud APIs"]
    PROTO["Protocol nodes<br/>SSH, Shadowsocks, Outline,<br/>Trojan, V2Ray, HTTP proxy"]
  end

  subgraph External
    DNSP["DNS providers"]
    PAY["Payment gateways"]
    TG["Telegram API"]
  end

  EU --> PORTAL
  EU --> BOTS
  RS --> DASH
  RS --> BOTS
  SA --> DASH
  SA --> BOTS

  PORTAL --> CP
  DASH --> CP
  BOTS --> CP

  CP --> FLUX
  CP --> PROTO
  CP --> DNSP
  CP --> PAY
  CP --> TG
  FLUX --> PROTO
```

**Reading the diagram:** only the control plane talks to the platform, DNS and payment
providers. End users never receive platform credentials; they receive protocol
credentials issued by the control plane.

## Containers

```mermaid
flowchart LR
  subgraph Browser
    NEXT["Next.js dashboard<br/>admin-dashboard/"]
  end

  subgraph Backend
    API["API process<br/>worker_api/app/main.py"]
    TASKS["Celery workers<br/>worker_api/app/tasks/"]
    BEAT["Celery beat<br/>periodic schedules"]
  end

  subgraph State
    PG[("PostgreSQL<br/>43 migrations")]
    RD[("Redis<br/>broker, cache,<br/>rate limits")]
  end

  subgraph Nodes
    N1["protocol container"]
    N2["protocol container"]
  end

  NEXT -->|"HTTPS /api/v1"| API
  API --> PG
  API --> RD
  TASKS --> PG
  TASKS --> RD
  BEAT --> RD
  TASKS -->|"deploy, poll, sync"| N1
  TASKS --> N2
```

| Container | Source | Responsibility |
| --- | --- | --- |
| Dashboard | [`admin-dashboard/`](../admin-dashboard/) | Server-rendered UI, client components, API proxying, in-app help |
| API | [`worker_api/`](../worker_api/) | REST surface under `/api/v1`, schema migrations, health endpoints |
| Workers | [`worker_api/app/tasks/`](../worker_api/app/tasks/) | Billing, provisioning, DNS sync, telemetry, notifications |
| Protocol nodes | [`integrations/`](../integrations/) | Upstream VPN engines with a shared bootstrap contract |
| Bot | [`telegram_bot/`](../telegram_bot/) | Standalone Telegram process used by operators |

## Component view of the API

```mermaid
flowchart TB
  subgraph Routers["API layer — app/api/v1/endpoints/"]
    R1["auth / auth_v2"]
    R2["users / end_user / subscriptions"]
    R3["payments / webhooks / user_orders_api"]
    R4["admin* / super_admin / packages"]
    R5["fdm / nodes / ip_management"]
    R6["internal_v2 / reseller_bot_webhook / bot_config_api"]
  end

  subgraph Services["Domain services — app/services/"]
    S1["credentials, auth, routing"]
    S2["billing, payments, orders, referral"]
    S3["flux, fdm, regions, tlds"]
    S4["usage, monitoring, notifications, broadcasts"]
    S5["bots, free_config, compliance, autoscaling"]
  end

  subgraph Data["Persistence — app/models/, app/core/"]
    M1[("SQLAlchemy models")]
    M2["core/database.py, core/crypto.py, core/auth/"]
  end

  Routers --> Services --> Data
```

Routers should stay thin: validate, authorise, delegate. Business rules belong in the
service modules, and anything that must be repeatable or slow belongs in a task.

Full detail: [backend](architecture/backend.md) ·
[dashboard](architecture/dashboard.md) ·
[integrations](architecture/integrations.md).

## RunOnFlux integration surface

```mermaid
flowchart LR
  CTRL["Control plane"]
  AUTH["secp256k1 signing<br/>services/flux/client.py"]
  SPEC["app specification<br/>scripts/dev/generate_app_spec.py"]
  DEPLOY["deploy / update<br/>services/flux/client.py"]
  DISC["instance discovery<br/>services/flux/node_discovery.py"]
  HEALTH["health monitor<br/>services/flux/health_monitor.py"]
  NODE["node-level API<br/>services/flux/node_client.py"]
  FDM["domain discovery<br/>services/fdm/flux_discovery.py"]

  CTRL --> AUTH --> DEPLOY
  CTRL --> SPEC --> DEPLOY
  CTRL --> DISC --> HEALTH
  HEALTH --> NODE
  DISC --> FDM
  CTRL --> FDM
```

Detail, including the authentication chain and resilience settings:
[RunOnFlux platform integration](architecture/flux-platform.md).

## Cross-cutting concerns

| Concern | Where it lives | Notes |
| --- | --- | --- |
| Configuration | [`worker_api/app/core/config.py`](../worker_api/app/core/config.py) | Pydantic settings loaded from the environment; see [CONFIGURATION.md](CONFIGURATION.md) |
| Authentication | [`worker_api/app/core/auth/`](../worker_api/app/core/auth/) | JWT issuance/verification, password hashing, role dependencies |
| Session transport | [`worker_api/app/core/security.py`](../worker_api/app/core/security.py) | JWT bearer auth plus an internal service key |
| Secret encryption | [`worker_api/app/core/crypto.py`](../worker_api/app/core/crypto.py) | AES-GCM at rest for stored bot tokens |
| Data access | [`worker_api/app/core/database.py`](../worker_api/app/core/database.py) | Engine/session factory with per-session Postgres guards |
| Caching and limits | [`worker_api/app/core/redis_client.py`](../worker_api/app/core/redis_client.py) | Optional Redis-backed client |
| Scheduling | [`worker_api/app/core/celery_config.py`](../worker_api/app/core/celery_config.py) | Celery app, queues and periodic schedules |
| Migrations | [`worker_api/alembic/`](../worker_api/alembic/) | Linear Alembic history, applied by `start.sh` |
| Observability | [`worker_api/app/services/monitoring/`](../worker_api/app/services/monitoring/) | Metrics plus optional Sentry |

## Deployment topology (conceptual)

```mermaid
flowchart LR
  LB["TLS termination"] --> DASHX["dashboard container"]
  LB --> APIX["api container"]
  APIX --> PGX[("managed PostgreSQL")]
  APIX --> RDX[("managed Redis")]
  WORKX["worker container"] --> PGX
  WORKX --> RDX
  BEATX["beat container"] --> RDX
  WORKX --> FLUXX["RunOnFlux platform"]
```

This shows the intended shape only. No deployment automation, reverse-proxy
configuration, TLS setup, secret manager integration or backup policy is included in
this snapshot. See [DEPLOYMENT.md](DEPLOYMENT.md).

## What these diagrams deliberately omit

- **No infrastructure values.** Addresses, domains, node identifiers and credentials are
  omitted; placeholders are synthetic.
- **No runtime guarantees.** Relationships are derived from source, not from observing a
  running system.
- **No exact endpoint inventory.** The [API](API.md) document describes groups and roles;
  the code is the authority for individual routes.

## Where to go next

- New to the codebase: [Development](DEVELOPMENT.md), then [backend](architecture/backend.md).
- Evaluating fitness: [Capabilities](FEATURES.md), then [Deployment](DEPLOYMENT.md).
- Threat modelling: [Security model](SECURITY-MODEL.md).
- Explaining a behaviour: [Request flows](architecture/request-flows.md).