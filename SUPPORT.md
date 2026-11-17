# Support

## What this repository is

An **experimental, source-only snapshot** of an independent VPN control plane for the
RunOnFlux / FluxCloud platform. It is maintained on a best-effort basis by its
maintainers. There is no commercial support contract, no service-level agreement and no
guaranteed response time.

## What is supported

| Request | Where it goes |
| --- | --- |
| Bug in the code in this repository | [Open an issue](.github/ISSUE_TEMPLATE/bug_report.yml) |
| Feature or improvement idea | [Open an issue](.github/ISSUE_TEMPLATE/feature_request.yml) |
| Documentation correction or gap | Issue, or a pull request directly — see [CONTRIBUTING.md](CONTRIBUTING.md) |
| Security vulnerability | **Privately**, per [SECURITY.md](SECURITY.md) — never a public issue |
| Conduct concern | Private route described in [SECURITY.md](SECURITY.md) |
| Help installing or operating a deployment | Community-only; see "Not supported" below |
| RunOnFlux platform account, billing or node questions | RunOnFlux itself — this project is independent and cannot answer for the platform |

## Not supported

Please do not file issues for these:

- **Deployment, provisioning or uptime assistance.** This snapshot ships no verified
  deployment path; [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) explains exactly what is
  missing.
- **Live service or customer-data problems.** Maintainers have no access to your
  deployment and cannot investigate your users, wallets or nodes.
- **Upstream protocol engines.** SSH, Shadowsocks, Outline, Trojan, V2Ray, Squid and
  base images are third-party software; report their defects upstream. See
  [THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md).
- **Third-party gateway accounts.** Stripe, the crypto payment gateway, the Iranian
  payment gateway, Telegram and DNS providers are your own commercial relationships.
- **Licensing or legal advice.** The rights position of this snapshot is unresolved; see
  [THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md) and engage your own counsel.

## Writing a good issue

A useful report lets a maintainer reproduce the problem without asking follow-up
questions. Include:

1. **What you did** — exact commands or dashboard steps.
2. **What you expected** and **what actually happened**, including the full error text.
3. **Which part of the tree** is involved (path, endpoint or dashboard route).
4. **How you verified** — for example whether you ran the service-free safety suite.
5. **Redact everything sensitive** — no tokens, wallet keys, connection strings, real
   domains, phone numbers, handles or customer records. Replace them with obviously
   synthetic placeholders.

Screenshots are welcome only if you have removed all personal and operator data.

## Before opening an issue

- Search existing issues, including closed ones.
- Read the relevant document in the [documentation index](docs/README.md) — several
  common questions are answered there, particularly
  [docs/FEATURES.md](docs/FEATURES.md) (what is and is not implemented) and
  [docs/TESTING.md](docs/TESTING.md) (how to run tests without a live stack).
- Confirm the problem is in this repository rather than in your own configuration,
  network, or a third-party service.
