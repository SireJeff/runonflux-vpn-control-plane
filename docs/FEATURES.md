# Capabilities

What this codebase actually contains, and how much confidence the source alone justifies.

## How to read the ratings

| Rating | Means |
| --- | --- |
| **Implemented** | Source covers the documented flow end to end within this repository |
| **Partial** | Only some paths exist, or the flow needs configuration/services you must supply |
| **Unverified** | Source is present, but the capability depends on a live third party or has no execution proof for this snapshot |

None of these ratings mean "production ready". No install, migration, image build or live
traffic test was performed for this snapshot. See
[DEPLOYMENT.md](DEPLOYMENT.md) for the gap between "code exists" and "runs".

## Delivery

| Capability | Rating | Where | Notes |
| --- | --- | --- | --- |
| SSH access delivery | Partial | `integrations/ssh/`, `services/credentials/` | Real-time PAM validation path exists; no traffic test |
| Shadowsocks delivery | Partial | `integrations/shadowsocks/` | Config template plus periodic user sync |
| Outline delivery | Partial | `integrations/outline/` | Depends on the upstream Outline server behaviour |
| Trojan delivery | Partial | `integrations/trojan/` | Periodic user sync |
| V2Ray (VLESS/VMess) delivery | Partial | `integrations/v2ray/` | Periodic user sync; Xray-based |
| HTTP proxy delivery | Partial | `integrations/http-proxy/` | Squid external ACL validation |
| Connection strings | Implemented | `services/credentials/connection_string_service.py` | Per-protocol formatting |
| Credential rotation / reset | Implemented | `services/credentials/credential_service.py` | Reissue rather than mutate |
| Username generation | Implemented | `services/credentials/username_generator.py` | Deterministic scheme for node-side files |
| Routing presets | Partial | `services/credentials/routing_presets.py` | Presets exist; behaviour depends on client support |
| Deployment-token bootstrap | Implemented | `services/auth/deployment_tokens.py` | Short-lived node credentials |

## Accounts and subscriptions

| Capability | Rating | Where | Notes |
| --- | --- | --- | --- |
| Super-admin, reseller and end-user roles | Implemented | `core/auth/role_dependencies.py` | JWT role claims resolved against the database |
| Registration and approval of resellers | Implemented | `endpoints/auth_v2.py`, `endpoints/admin.py` | Approval is a platform action |
| Packages with pricing and quota | Implemented | `services/subscriptions/package_seeder.py`, `models/admin_packages.py` | Seeding plus manual management |
| Subscription lifecycle | Implemented | `services/subscriptions/` | Renewal, adjustment and expiry modules |
| Regions with per-region billing | Implemented | `services/regions/`, `services/billing/region_billing_service.py` | Primary region free, additional regions billed |
| Usage quotas | Partial | `services/usage/`, `services/billing/` | Enforcement depends on the billing pass running |
| Free trial | Partial | `ENABLE_FREE_TRIAL`, `TRIAL_DURATION_DAYS` | Feature-flagged; no runtime proof |
| User suspension and deletion | Implemented | `services/compliance/user_deletion.py` | Retention window configurable |

## Money

| Capability | Rating | Where | Notes |
| --- | --- | --- | --- |
| Reseller wallet with a ledger | Implemented | `services/billing/wallet_service.py`, `user_wallet_ledger.py` | Derive balance from entries |
| Traffic billing | Implemented | `services/billing/traffic_billing_service.py` | Reads telemetry counters |
| Wire top-up request and approval | Implemented | `services/billing/wire_order_service.py` | Approval is the money-mutating step |
| Exchange-rate conversion | Implemented | `services/billing/conversion.py` | Rate source is external |
| Stripe (international cards) | Unverified | `services/payments/stripe_gateway.py` | Requires live account, webhook secret |
| NOWPayments (crypto) | Unverified | `services/payments/nowpayments.py` | Requires live API key and IPN secret |
| Zarinpal (Iranian gateway) | Unverified | `services/payments/zarinpal.py` | Requires live merchant ID |
| Payment webhooks | Implemented | `endpoints/webhooks.py` | Signature handling per gateway |
| Order receipts and review | Implemented | `services/orders/` | Receipt storage plus approval flow |
| Manual wallet adjustments | Implemented | `models/user_adjustments.py` | Corrections are new entries |
| Referral bonuses | Implemented | `services/referral/` | Feature-flagged |
| Wallet withdrawals | Partial | `ENABLE_WALLET_WITHDRAWALS` | Flag exists; payout out of scope |

## Bots and messaging

| Capability | Rating | Where | Notes |
| --- | --- | --- | --- |
| Reseller-owned Telegram bots | Implemented | `services/bots/reseller_bot_manager.py` | Token stored encrypted |
| Single webhook for all bots | Implemented | `endpoints/reseller_bot_webhook.py` | Timing-safe secret check |
| Bot-facing internal API | Implemented | `endpoints/internal_v2.py` | Internal key required |
| End-user chat flows (buy, connections, wallet, referral) | Implemented | `services/bots/`, `telegram_bot/bot/handlers/` | Persian and English |
| Bot config management | Implemented | `endpoints/bot_config_api.py`, `/dashboard/bot-config` | Update without re-registering |
| Platform bot oversight | Implemented | `endpoints/super_admin_bots_api.py` | List, inspect webhook, re-register |
| Broadcasts | Implemented | `services/broadcasts/`, `endpoints/broadcast_api.py` | Daily cap and staleness rules |
| Notifications (SMTP, Telegram) | Implemented | `services/notifications/` | Templated bilingual messages |
| Standalone bot process | Partial | `telegram_bot/` | Separate dependency environment; single nav test |

## Domains, DNS and IPs

| Capability | Rating | Where | Notes |
| --- | --- | --- | --- |
| TLD registry and activation | Implemented | `services/tlds/`, `models/registered_tld.py` | Add, activate, deactivate, delete |
| DNS provider abstraction | Implemented | `services/fdm/dns_provider.py` | Provider-specific clients below it |
| ArvanCloud integration | Unverified | `services/fdm/arvancloud_client.py` | Requires API key and a zone |
| Cloudflare integration | Unverified | `services/fdm/cloudflare_client.py` | Requires token and zone |
| Convergent sync (skip healthy records) | Implemented | `services/fdm/fdm_sync_service.py` | Protects shared provider rate limits |
| Liveness checking | Implemented | `services/fdm/liveness.py` | Dead-fraction guard before mass action |
| Reachability probing | Partial | `services/fdm/iran_reach.py` | Many tuning knobs; no live validation |
| Per-TLD analytics | Implemented | `tasks/tld_analytics.py`, `models/tld_usage_daily.py` | Daily rollups |
| IP pool management | Implemented | `endpoints/ip_management.py`, `services/` | Assignment plus health records |
| Proxy route management | Partial | `services/tlds/proxy_routes.py` | Depends on node-side configuration |

## Platform (RunOnFlux / FluxCloud)

| Capability | Rating | Where | Notes |
| --- | --- | --- | --- |
| Wallet-signed API authorization | Implemented | `services/flux/client.py` | secp256k1 signing with recovery byte |
| Application spec generation | Implemented | `scripts/dev/generate_app_spec.py` | Requires explicit inputs and key |
| Deploy / update applications | Unverified | `services/flux/client.py` | Needs a live platform |
| Instance discovery | Unverified | `services/flux/node_discovery.py` | Needs live nodes |
| Node-level API operations | Unverified | `services/flux/node_client.py` | Needs node authorization |
| Health monitoring | Unverified | `services/flux/health_monitor.py` | Needs live nodes |
| Multi-node consensus | Implemented | `services/flux/consensus_manager.py` | Threshold configurable |
| Retry and circuit breaking | Implemented | `services/flux/resilience.py` | Tunable via `FLUX_*` |
| Autoscaling by load and health | Partial | `services/autoscaling/autoscaler.py` | Redis-coordinated; no live validation |
| Domain discovery feed | Partial | `services/fdm/flux_discovery.py` | Consumed by DNS automation |

## Operations and insight

| Capability | Rating | Where | Notes |
| --- | --- | --- | --- |
| Traffic counters and rollups | Implemented | `services/usage/`, `models/traffic_*` | Fed by node telemetry |
| Live connection views | Implemented | `services/usage/live_connections.py` | Per-user active counts |
| Health and performance metrics | Implemented | `services/monitoring/health_metrics.py` | Buffered, admin-facing |
| Structured logging | Implemented | `models/logging.py`, `models/observability.py` | Queryable audit trail |
| Support tickets | Implemented | `services/` + `/dashboard/support` | Threaded conversations |
| Admin dashboard analytics | Implemented | `/dashboard/analytics`, `/super/analytics` | Over the metrics models |
| Broadcast analytics | Partial | `services/broadcasts/` | Delivery tracking depends on Telegram |
| Dashboard health endpoint | Implemented | `admin-dashboard/app/api/health/` | Container liveness |
| Migrations at boot | Implemented | `worker_api/start.sh` | Aborts startup on failure |
| Disposable test stack | Implemented | `docker-compose.test.yml`, `scripts/test.sh` | Local daemon only, refuses remote |
| Documentation integrity | Partial | reviewer-run checks | Relative links, fences, diagrams and help anchors; not automated in this snapshot |

## Explicitly out of scope for this snapshot

| Not included | Consequence |
| --- | --- |
| Production deployment automation | You must design provisioning, TLS, secrets and backups |
| Reverse-proxy / ingress configuration | Not provided |
| Container hardening (seccomp, read-only root, capability drops) | Not provided |
| Backup, restore and disaster recovery | Not provided |
| Monitoring stack (dashboards, alerts, on-call) | Only in-process metrics exist |
| Load or soak test results | None |
| Migration rehearsal against a fresh database | None |
| Protocol end-to-end traffic tests | None |
| Legal, licensing or data-processing artefacts | Unresolved; see [THIRD_PARTY_REVIEW](../THIRD_PARTY_REVIEW.md) |

## How to use this table

- Treat **Implemented** as "the source intends to do this" and **Unverified** as "do not
  assume it works until you have run it in your own environment".
- Every **Unverified** row is a dependency on a third party: a payment gateway, a DNS
  provider, or the RunOnFlux platform. Those need your own accounts and your own testing.
- If a capability you need is listed as out of scope, plan to build and document it
  yourself — and consider contributing the result.