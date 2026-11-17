# Documentation

This index is the entry point for everything in this repository. Documents are grouped
by what you are trying to do, not by file type.

> **Read this first:** the repository is an **experimental source snapshot**. Nothing
> here has been verified by a fresh install, a migration run, an image build or live
> protocol traffic. See [DEPLOYMENT.md](DEPLOYMENT.md) for exactly what is missing and
> [FEATURES.md](FEATURES.md) for what is implemented versus unproven.

## Understand the system

| Document | Answers |
| --- | --- |
| [Architecture overview](ARCHITECTURE.md) | What the pieces are and how a request moves through them |
| [Backend](architecture/backend.md) | API layers, service domains, background tasks, auth and data access |
| [Dashboard](architecture/dashboard.md) | Route map, API client, localisation and the help-guide pipeline |
| [Protocol integrations](architecture/integrations.md) | How protocol containers are built, configured and authenticated |
| [RunOnFlux platform integration](architecture/flux-platform.md) | Authentication, app specifications, discovery and health monitoring |
| [Data model](architecture/data-model.md) | Entity groups and the relationships that matter |
| [Request flows](architecture/request-flows.md) | Sequence diagrams for the main end-to-end paths |
| [Capabilities](FEATURES.md) | Every subsystem, what it does, and how mature it is |
| [Glossary](GLOSSARY.md) | Terms such as reseller, end user, TLD, FDM and free-config |

## Work on the code

| Document | Answers |
| --- | --- |
| [Development](DEVELOPMENT.md) | Environment setup, quality gates, conventions |
| [Configuration](CONFIGURATION.md) | Environment variables, which are required, and what they affect |
| [API](API.md) | Endpoint groups, roles and error conventions |
| [Testing](TESTING.md) | Test layers, isolation rules and what is not covered |
| [Contributing](../CONTRIBUTING.md) | How to propose and submit a change |
| [Changelog](../CHANGELOG.md) | What changed in this repository |

## Operate it

| Document | Answers |
| --- | --- |
| [Super-admin guide](platform/SUPERADMIN_GUIDE.md) | Platform-level operation through the dashboard and bot |
| [Reseller guide](platform/SUBADMIN_GUIDE.md) | Reseller operation end to end |
| [Deployment](DEPLOYMENT.md) | What you must build yourself, and what to verify first |
| [Security model](SECURITY-MODEL.md) | Trust boundaries and how secrets are handled |
| [Security policy](../SECURITY.md) | How to report a vulnerability |
| [Support](../SUPPORT.md) | What this project can and cannot help with |

## Conventions used in these documents

- **Paths** are repository-relative and linked, so you can jump straight to the code.
- **Maturity ratings** in [FEATURES.md](FEATURES.md) are deliberately blunt:
  *Implemented* (source covers the documented flow), *Partial* (only some paths, or
  dependent on configuration you must supply), *Unverified* (source present, but depends
  on a live third party or has no execution proof for this snapshot).
- **Diagrams** are Mermaid source, so they render on GitHub and stay reviewable in a
  diff.
- **No operational values.** Example domains, phone numbers and identifiers are
  reserved or obviously synthetic. Anything that looks like a real operator value is a
  documentation bug — please report it.