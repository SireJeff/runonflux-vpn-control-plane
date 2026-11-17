# API

The backend is a FastAPI application mounted under `/api/v1`. Routers are grouped by
audience and authorization level, not by resource type.

> **No per-route reference is published here.** The authoritative list is the code in
> [`worker_api/app/api/v1/endpoints/`](../worker_api/app/api/v1/endpoints/). Interactive
> OpenAPI documentation is generated at `/api/docs` **only when `DEBUG` is enabled**, so
> it is not available in a hardened deployment.

## Endpoint groups

| Group | Audience | Authorization | Example router |
| --- | --- | --- | --- |
| Authentication | Everyone | None | `auth_v2.py` |
| Platform administration | Super admin | `super_admin` role | `admin.py`, `super_admin_bots_api.py`, `broadcast_api.py` |
| Reseller administration | Reseller | Reseller role, own data only | `users.py`, `wallet_api.py`, `orders_api.py`, `bot_config_api.py` |
| End-user portal | End user | End-user role, own data only | `user_orders_api.py`, `user_subscription_api.py` |
| Domains and IPs | Reseller and platform | Role plus ownership | `domains_api.py`, `ip_management.py` |
| Support | Reseller and platform | Role plus ownership | `support_api.py` |
| Usage and analytics | Reseller and platform | Role plus ownership | `usage_api.py`, `analytics_api.py` |
| Webhooks | Payment gateways | Gateway signature verification | `webhooks.py` |
| Bot webhook | Telegram | Secret header | `reseller_bot_webhook.py` |
| Internal | Nodes and bot process | `X-Internal-API-Key` | `internal_v2.py` |
| Migration | Super admin | `super_admin` role | `migrate.py` |
| Demonstration | Public | None | `mvp.py` |

`mvp.py` is explicitly labelled as simplified demonstration endpoints. Review whether you
want it reachable in a real deployment.

## Conventions

### Authentication

- Bearer JWT in the `Authorization` header. Access tokens are short-lived; refresh tokens
  are exchanged at the auth router.
- The role claim is re-resolved against the database on each request. A token whose role
  no longer matches the record is rejected.

### Status codes

| Code | Meaning in this API |
| --- | --- |
| `200` / `201` | Success |
| `400` | Validation or business-rule failure |
| `401` | Missing, expired or invalid token |
| `403` | Authenticated but not permitted for this record or role |
| `404` | Not found **or** not visible to the caller |
| `409` | State conflict (for example, already approved) |
| `422` | Request schema validation failure (FastAPI default) |
| `429` | Rate limit exceeded |
| `500` | Unhandled server error |

`404` is used deliberately for records the caller may not see, so existence is not leaked
across reseller boundaries.

### Request shape

- JSON bodies; timestamps are ISO-8601 with timezone.
- Money is sent as decimal strings to avoid float rounding; read responses as decimals.
- Pagination is query-parameter based; list responses include a total where the endpoint
  supports it.

### Idempotency

- Money-moving endpoints (approval, credit, adjustment) are safe to retry: an already
  applied operation returns a conflict rather than double-applying.
- Node-facing endpoints tolerate repeated syncs.

### Rate limiting

Redis-backed per-window limits guard authentication and expensive reads. Limits are a
brake on abuse, not an authorization mechanism.

## Machine callers

Nodes and the bot process call the internal group with the `X-Internal-API-Key` header.
These endpoints:

- never accept a user token as a substitute,
- return only the user set or telemetry scope the caller needs,
- are expected to be reachable only from your own network.

## Webhooks

| Webhook | Verification |
| --- | --- |
| Payment gateways | Provider-specific signature or secret check |
| Telegram | `X-Telegram-Bot-Api-Secret-Token`, timing-safe comparison |
| Internal node callbacks | Internal API key |

Verify the gateway's current signing scheme against its documentation before exposing a
webhook endpoint; schemes change and an unverified webhook is an open door.

## Errors and observability

- Errors return a JSON body with a message; internal details are not echoed to clients.
- Requests are timed and buffered into admin health metrics.
- Structured logs record actor, action and target for auditable operations.

## Versioning

The prefix `/api/v1` is the only version contract in this snapshot. There is no
deprecation policy, no version negotiation and no compatibility guarantee between
releases — treat the API as experimental.

## Try it locally

```bash
DEBUG=true uvicorn app.main:app --reload --port 8080
# then open http://localhost:8080/api/docs
```

Never enable `DEBUG` on an internet-reachable deployment.

## Related documents

- [architecture/backend.md](architecture/backend.md) — router, service and task layout
- [architecture/request-flows.md](architecture/request-flows.md) — end-to-end sequences
- [SECURITY-MODEL.md](SECURITY-MODEL.md) — role boundaries and secret classes