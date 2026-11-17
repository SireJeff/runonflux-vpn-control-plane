# Configuration

Every setting is read from the environment by
[`worker_api/app/core/config.py`](../worker_api/app/core/config.py) (backend) or
[`admin-dashboard/`](../admin-dashboard/) (dashboard). [`.env.example`](../.env.example)
lists the same names with **empty values** — placeholders only, never real credentials.

**That file is the inventory; this page is the explanation.** If a variable is missing
here, read `config.py`.

## Values you must supply

These are empty in `.env.example` because they are deployment-specific or secret.

| Variable | Why it matters |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string (cache, rate limiting, autoscaler coordination) |
| `JWT_SECRET_KEY` | Signs access and refresh tokens |
| `FLUXVPN_SECRET_KEY` | Derives the AES-GCM key for stored bot tokens |
| `INTERNAL_API_KEY` | Shared secret between the API, nodes and the bot process |
| `SUPER_ADMIN_PASSWORD` | Bootstrap platform password; change after first login |
| `FLUX_WALLET_ADDRESS` | RunOnFlux wallet identity |
| `FLUX_WALLET_PRIVATE_KEY` | Signs platform authorization; treat as a signing key |
| `TELEGRAM_BOT_TOKEN` | Platform bot token from BotFather |
| `WEBHOOK_SECRET` | Secret token presented by Telegram on webhook calls |

Generate each secret independently. Reusing a value across deployments links them.

## Service addresses

| Variable | Purpose |
| --- | --- |
| `FLUXVPN_API_URL` | API base URL used by containers and the bot |
| `PUBLIC_API_BASE_URL` | Public API URL used in generated client configuration |
| `API_PROXY_URL` | Dashboard server-side proxy target |
| `NEXT_PUBLIC_API_URL` | Browser-visible API base path |
| `NEXT_PUBLIC_USER_PORTAL_DOMAIN` | End-user portal host used in links and messages |
| `USER_PORTAL_URL` | End-user portal base URL for messages |
| `ALLOWED_ORIGINS` | CORS allowlist; must be explicit in any deployment with credentials |

Anything prefixed `NEXT_PUBLIC_` is compiled into the browser bundle. Never put a secret
behind that prefix.

## RunOnFlux / FluxCloud

| Variable | Purpose |
| --- | --- |
| `FLUX_API_URL` | Platform API base URL |
| `FLUX_WALLET_ADDRESS`, `FLUX_WALLET_PRIVATE_KEY` | Authorization identity |
| `FLUX_RETRY_ATTEMPTS`, `FLUX_RETRY_BACKOFF_BASE` | Retry policy |
| `FLUX_CIRCUIT_BREAKER_THRESHOLD`, `FLUX_CIRCUIT_BREAKER_TIMEOUT` | Circuit breaker |
| `FLUX_NODE_DISCOVERY_ENABLED`, `FLUX_NODE_CACHE_TTL_HOURS` | Discovery and cache lifetime |
| `FLUX_NODE_MIN_CONSENSUS`, `FLUX_NODE_API_PORT`, `FLUX_NODE_TIMEOUT` | Node selection policy |
| `FLUX_INITIAL_NODES` | Bootstrap node list when discovery is unavailable |
| `FLUX_FDM_DISCOVERY_NODE_COUNT` | Discovery breadth for domain automation |

Behaviour and design rules: [architecture/flux-platform.md](architecture/flux-platform.md).

## DNS providers and domain automation

| Variable | Purpose |
| --- | --- |
| `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ZONE_ID` | Cloudflare credentials and zone |
| `ARVAN_API_KEY` | ArvanCloud credentials |
| `FDM_DOMAIN_AUTOMATION_ENABLED` | Master switch for DNS automation |
| `FDM_DEAD_FRACTION_THRESHOLD` | Guard against mass deletion after a liveness failure |
| `FDM_REACHABILITY_*` | Reachability probing tuning |
| `FDM_SYNC_INTERVAL_*` | Sync cadence |

Scope DNS tokens to the smallest zone set that works. A token that can edit every zone
turns one bug into an outage.

## Payment gateways

| Variable | Purpose |
| --- | --- |
| `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | International cards |
| `NOWPAYMENTS_API_KEY`, `NOWPAYMENTS_IPN_SECRET` | Crypto payments |
| `ZARINPAL_MERCHANT_ID` | Iranian gateway |
| `EXCHANGE_RATE_API_URL` | Rate source used for currency conversion |

Each gateway is optional; leave its block empty to disable it. Configure only what you
actually use, and verify webhook signature handling against the provider's current
documentation.

## Notifications and email

| Variable | Purpose |
| --- | --- |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | Outbound email |
| `SMTP_USE_TLS` | Transport security |
| `TELEGRAM_BOT_TOKEN`, `WEBHOOK_SECRET` | Bot identity and webhook verification |

## Feature flags and limits

| Variable | Purpose |
| --- | --- |
| `ENABLE_FREE_TRIAL`, `TRIAL_DURATION_DAYS` | Trial subscriptions |
| `ENABLE_WALLET_WITHDRAWALS` | Withdrawal surface |
| `ENABLE_FREE_CONFIG` | Free-configuration enrolment |
| `RATE_LIMIT_*` | Request rate limits |
| `BROADCAST_*` | Daily broadcast caps and staleness rules |
| `ADMIN_METRICS_*` | Admin metrics buffering |
| `TRAFFIC_*` | Traffic accounting behaviour |

Flags are read at startup unless the code re-reads them; changing one usually needs a
restart.

## Runtime and observability

| Variable | Purpose |
| --- | --- |
| `DEBUG` | Verbose logging **and** the interactive `/api/docs` endpoint |
| `ENVIRONMENT` | Deployment label used by logging and guards |
| `LOG_LEVEL` | Log verbosity |
| `SENTRY_DSN` | Optional error reporting |
| `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` | Worker transport (often derived from `REDIS_URL`) |

## Rules for changing configuration

1. **Defaults must be safe.** A missing secret should fail closed, not fall back to a
   working value.
2. **`DEBUG` off in anything reachable.** It exposes interactive API documentation.
3. **`FLUXVPN_SECRET_KEY` rotation is a migration.** It derives the key for stored bot
   tokens; rotating without re-encryption breaks decryption.
4. **`JWT_SECRET_KEY` rotation logs everyone out.** Plan it as a maintenance action.
5. **`INTERNAL_API_KEY` rotation is fleet-wide.** Update the API, every node and the bot
   together.
6. **Never commit a filled `.env`.** `.gitignore` covers the usual names; keep it that way.

## Related documents

- [DEVELOPMENT.md](DEVELOPMENT.md) — local setup and quality gates
- [SECURITY-MODEL.md](SECURITY-MODEL.md) — secret classes and rotation consequences
- [DEPLOYMENT.md](DEPLOYMENT.md) — what a real deployment still needs
- [architecture/flux-platform.md](architecture/flux-platform.md) — platform integration detail