# Request flows

Sequence diagrams for the paths that matter most. Each one names the modules involved so
you can read the code alongside the diagram.

> These flows describe **intended source behaviour**. They are derived from reading the
> code, not from observing a running deployment.

## 1. End-user purchase and provisioning

```mermaid
sequenceDiagram
  actor EU as End user
  participant BOT as Reseller bot<br/>or /user portal
  participant API as Control plane
  participant DB as PostgreSQL
  participant NODE as Protocol node

  EU->>BOT: buy(package) / choose region
  BOT->>API: create order
  API->>DB: UserOrder (pending)
  EU->>BOT: upload payment receipt
  BOT->>API: attach receipt
  Note over API: order waits for reseller approval
  EU->>BOT: my subscription
  BOT->>API: read subscription state
  API-->>BOT: pending
  Note over API,DB: reseller approves in /dashboard/orders
  API->>DB: order approved, subscription created
  API->>DB: credentials issued
  API-->>BOT: delivery payload
  BOT-->>EU: connection details
  NODE->>API: sync active users (next interval)
  API-->>NODE: user set + credentials
  EU->>NODE: connect with issued credentials
```

Modules: `services/orders`, `services/subscriptions`, `services/credentials`,
`api/v1/endpoints/user_orders_api.py`, `api/v1/endpoints/internal_v2.py`, bot handlers in
[`telegram_bot/bot/handlers/`](../../telegram_bot/bot/handlers/).

Two properties are worth preserving: an order never provisions before approval, and
delivery is idempotent so a retried approval does not issue duplicate credentials.

## 2. Reseller wallet top-up (wire transfer)

```mermaid
sequenceDiagram
  actor RS as Reseller
  actor SA as Super admin
  participant UI as /dashboard/wallet
  participant SUI as /super/orders
  participant API as Control plane
  participant DB as PostgreSQL

  RS->>UI: submit wire top-up request
  UI->>API: create wire order (amount, reference)
  API->>DB: wire_orders (pending)
  SA->>SUI: review pending top-up
  SUI->>API: approve with exchange rate
  API->>DB: wallet transaction (credit)
  API->>DB: wire_orders (approved)
  API-->>RS: notification
  RS->>UI: view ledger
  UI->>API: read transactions
  API-->>UI: derived balance + entries
```

Modules: `services/billing/wire_order_service.py`,
`services/billing/wallet_service.py`, `services/billing/conversion.py`.

Approval is the money-mutating step, so it must be safe to retry and must record who
approved what, at which rate, leaving an auditable entry rather than mutating a balance.

## 3. Free-config enrollment

```mermaid
sequenceDiagram
  actor EU as End user
  participant BOT as Reseller bot
  participant API as Control plane
  participant DB as PostgreSQL
  participant NODE as Protocol node

  EU->>BOT: request free configuration
  BOT->>API: enrollment request
  API->>DB: read channel policy + global limits
  alt eligible
    API->>DB: create enrollment
    API->>DB: issue limited credential
    API-->>BOT: configuration
    BOT-->>EU: configuration
  else not eligible
    API-->>BOT: refusal reason
    BOT-->>EU: explanation
  end
  NODE->>API: sync active users
  API-->>NODE: includes enrolled user
```

Modules: `services/free_config/` (`policy.py`, `enrollment_service.py`,
`membership_verifier.py`, `global_service.py`), models `free_config_channel`,
`free_config_enrollment`, `free_config_global`.

Policy is evaluated server-side. Client-side checks are convenience only — never the
authority for quota or eligibility.

## 4. Domain and DNS synchronisation (FDM)

```mermaid
sequenceDiagram
  participant BEAT as Celery beat
  participant TASK as fdm_tasks
  participant SVC as fdm_domain_service
  participant PROV as DNS provider
  participant LIVE as liveness / reachability
  participant DB as PostgreSQL

  BEAT->>TASK: scheduled sync
  TASK->>SVC: reconcile desired state
  SVC->>DB: read TLDs and IP pools
  SVC->>PROV: create/update/remove records
  PROV-->>SVC: provider result
  SVC->>DB: record outcome
  TASK->>LIVE: check liveness / reachability
  LIVE->>DB: update health
  TASK->>DB: write daily TLD analytics
```

Modules: `services/fdm/` (`fdm_domain_service.py`, `fdm_sync_service.py`,
`dns_provider.py`, `arvancloud_client.py`, `cloudflare_client.py`, `liveness.py`,
`iran_reach.py`), `tasks/fdm_tasks.py`, `tasks/tld_analytics.py`.

Constraints that matter operationally: provider rate limits are shared across all
domains, so the sync skips already-converged records instead of rewriting everything each
cycle; and a mass liveness failure must not be interpreted as "delete everything" — the
dead-fraction guard exists for that reason.

## 5. Bot registration and webhook dispatch

```mermaid
sequenceDiagram
  actor RS as Reseller
  participant UI as /dashboard/bot-config
  participant API as Control plane
  participant DB as PostgreSQL
  participant TG as Telegram
  participant WH as reseller_bot_webhook

  RS->>UI: submit bot token
  UI->>API: register bot
  API->>DB: admin_bots (encrypted token)
  API->>TG: setWebhook(secret token)
  TG-->>API: ok
  Note over TG,WH: user messages a reseller bot
  TG->>WH: update + secret header
  WH->>WH: verify secret (timing-safe)
  WH->>DB: resolve bot -> reseller context
  WH->>API: dispatch update to bot application
  API->>TG: reply
```

Modules: `api/v1/endpoints/bot_config_api.py`,
`api/v1/endpoints/reseller_bot_webhook.py`, `services/bots/reseller_bot_manager.py`,
[`telegram_bot/bot/main.py`](../../telegram_bot/bot/main.py).

Bot tokens are stored encrypted (see
[`worker_api/app/core/crypto.py`](../../worker_api/app/core/crypto.py)) and are never
returned to the browser after registration. One webhook endpoint serves every reseller
bot, so routing must resolve the bot before any handler runs.

## 6. Node bootstrap

```mermaid
sequenceDiagram
  participant C as Protocol container
  participant API as Control plane
  participant DB as PostgreSQL

  C->>API: bootstrap with deployment token
  API->>API: verify token signature + expiry
  API->>DB: record instance
  API-->>C: accepted
  loop sync
    C->>API: fetch users (X-Internal-API-Key)
    API-->>C: user set
    C->>API: report usage
  end
```

Modules: `services/auth/deployment_tokens.py`,
`api/v1/endpoints/internal_v2.py`,
[`integrations/base/entrypoint-wrapper.sh`](../../integrations/base/entrypoint-wrapper.sh).

A node that cannot bootstrap must not start its engine: unattributed traffic is worse than
downtime.

## Reading these critically

- Failure branches are summarised, not exhaustive; the code is the authority.
- No flow here has been executed end to end for this snapshot.
- Where a flow touches money or credentials, assume retries happen: idempotency is a
  requirement, not a nicety.