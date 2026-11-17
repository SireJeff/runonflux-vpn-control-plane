# Glossary

Terms used across this repository. Where a term maps to a specific model or module, that
is noted — naming in the code does not always match the product language.

## Actors

| Term | Meaning |
| --- | --- |
| **Super admin** | Platform owner. Manages resellers, pricing, domains and platform applications. Model: `SuperAdmin`; role claim `super_admin` |
| **Reseller** | Tenant that buys capacity and sells to its own end users. Model: `Admin`; role claim `admin` |
| **End user** | The person who buys a subscription and connects. Model: `AdminUser`; role claim `end_user` |
| **Reseller bot** | A Telegram bot registered by a reseller for its own end users |
| **Platform bot** | The operator-level Telegram bot used by the super admin |

> **Naming trap:** resellers are `Admin` records and end users are `AdminUser` records.
> `super_admin` is a role, not a separate table.

## Domains and routing

| Term | Meaning |
| --- | --- |
| **TLD** | A zone used to serve subscriptions. Model: `RegisteredTld` |
| **FDM** | Domain management subsystem: desired-state reconciliation against DNS providers. Services: `services/fdm/` |
| **Provider** | A DNS vendor implementing the provider interface (for example ArvanCloud or Cloudflare) |
| **Convergent sync** | Sync that skips records already in the desired state, protecting shared provider rate limits |
| **Liveness** | Whether a record resolves and the target answers at all |
| **Reachability** | Whether a target is usable from a particular vantage point (for example, from a specific national network) |
| **Dead fraction guard** | Threshold that stops the automation deleting records when a large share appear dead, which usually indicates a monitoring failure rather than a real outage |
| **Pinning** | Assigning a reseller to a specific TLD so its users are served from a chosen zone |

## Money

| Term | Meaning |
| --- | --- |
| **Wallet** | A reseller's prepaid balance, held as a **ledger** of entries rather than a mutable number: `wallet_transaction_v2` |
| **Wire order** | A manual top-up request that a super admin approves: `wire_orders` |
| **Ledger entry** | A single credit or debit; the balance is derived by summing entries |
| **Adjustment** | A corrective ledger entry: `user_adjustments` |
| **Traffic charge** | Debit derived from reported usage: `debit_traffic` |
| **Region charge** | Debit for an additional (non-primary) region: `debit_region` |
| **Primary region** | A user's first region; carries no separate region billing clock |
| **Order** | An end-user purchase awaiting reseller approval: `UserOrder` |
| **Receipt** | Proof of payment uploaded by an end user and reviewed by a reseller |
| **Conversion** | Currency conversion between the reseller's wallet currency and a charge or rate |

## Access and delivery

| Term | Meaning |
| --- | --- |
| **Credential** | A generated protocol account for one subscription: `Credential`, `UserCredentialV2` |
| **Connection string** | A per-protocol client configuration string (for example for V2Ray) |
| **Deployment token** | A short-lived token with which a protocol container bootstraps against the API |
| **Internal API key** | Shared secret used by nodes and the bot process for machine endpoints (`X-Internal-API-Key`) |
| **Routing rule** | Per-user routing configuration (for example split-tunnel presets) |
| **Telemetry sidecar** | A small HTTP server inside each protocol container exposing a uniform usage interface |
| **Node / instance** | One running protocol container, discovered through the platform or a configured list |

## Platform

| Term | Meaning |
| --- | --- |
| **RunOnFlux / FluxCloud** | The decentralised platform this project integrates with. This project is independent and unaffiliated |
| **Application** | A deployment unit on the platform; recorded as `flux_app_registration` |
| **Application specification** | The declarative description of an application (image, ports, resources, environment) sent to the platform |
| **ZelID** | The wallet identity used to authorize platform operations |
| **Consensus** | Cross-checking an answer from multiple nodes before trusting it (`consensus_manager`) |
| **Circuit breaker** | Failure-threshold mechanism that stops hammering a failing dependency (`resilience`) |

## Accounts and plans

| Term | Meaning |
| --- | --- |
| **Package** | A sellable bundle of quota and duration: `AdminPackage` |
| **Subscription** | An entitlement created by an approved order: `Subscription` |
| **Trial** | Feature-flagged free period: `ENABLE_FREE_TRIAL`, `TRIAL_DURATION_DAYS` |
| **Free config** | Feature-flagged free configuration issued under channel policy: `services/free_config/`, `FreeConfigChannel`, `FreeConfigEnrollment`, `FreeConfigGlobal` |
| **Referral** | Invite program awarding bonuses: `services/referral/`, `AdminReferral` |
| **Usage** | Reported traffic and connection counts: `traffic_counters`, `traffic_logs`, `usage_analytics` |

## Communications and support

| Term | Meaning |
| --- | --- |
| **Broadcast** | Bulk message campaign from a reseller or the platform: `Broadcast` |
| **Support thread** | A conversation between an end user and the reseller: `/dashboard/support` |
| **RTL** | Right-to-left presentation, required for Persian |

## Release and repository terms

| Term | Meaning |
| --- | --- |
| **Snapshot** | This curated public source export; not a tagged release and not built from private history |
| **Snapshot export** | How this public tree was assembled from reviewed inputs; the assembly tooling is maintainer-side and not part of the snapshot |
| **Manifest** | [`SOURCE_MANIFEST.json`](../SOURCE_MANIFEST.json) — per-file hashes and transforms for this snapshot |
| **Provenance** | Where a file came from and what was done to it, as recorded in the manifest |
| **Safety suite** | The dependency-free test layer that must run anywhere |
| **Documentation check** | Review step verifying relative links, fenced blocks, diagrams and help anchors before a documentation change is accepted |

## Ratings

| Rating | Meaning |
| --- | --- |
| **Implemented** | Source covers the documented flow within this repository |
| **Partial** | Only some paths, or depends on configuration you must supply |
| **Unverified** | Source present, but depends on a live third party or has no execution proof here |

See [FEATURES.md](FEATURES.md) for the ratings applied per capability.