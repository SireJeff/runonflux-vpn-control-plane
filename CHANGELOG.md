# Changelog

All notable changes to this repository are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project intends to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it leaves the experimental stage.

> **Scope note.** This repository is a curated public snapshot. Development history
> before publication is not represented here, and the private operational repository
> this snapshot was derived from is not part of this changelog. Entries below describe
> changes to *this* repository only.

## [Unreleased]

### Added

- Expanded documentation set: architecture hub with system, container, component,
  data-model and request-flow diagrams.
- Capability catalogue with an explicit maturity rating per subsystem
  ([docs/FEATURES.md](docs/FEATURES.md)).
- Security model overview ([docs/SECURITY-MODEL.md](docs/SECURITY-MODEL.md)).
- Developer documentation: setup, quality gates
  ([docs/DEVELOPMENT.md](docs/DEVELOPMENT.md)), configuration reference
  ([docs/CONFIGURATION.md](docs/CONFIGURATION.md)), API map ([docs/API.md](docs/API.md)),
  testing guide ([docs/TESTING.md](docs/TESTING.md)) and deployment caveats
  ([docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)).
- Glossary of platform terms ([docs/GLOSSARY.md](docs/GLOSSARY.md)).
- Project governance documents: [CONTRIBUTING.md](CONTRIBUTING.md),
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md),
  [SUPPORT.md](SUPPORT.md).
- GitHub issue templates and a pull request template.
- Public operator documentation for the super-admin and reseller roles, replacing the
  placeholder guides while preserving their heading structure and in-app help anchors.
- Documentation review covering relative links, fenced blocks, Mermaid diagram bodies and
  help-map anchor integrity.

### Changed

- README restructured around purpose, capability summary, architecture diagram,
  quick start and documentation index.
- Third-party review expanded into a per-component inventory with explicit
  re-verification requirements.

### Notes

- No pinning, tagging or release artefact accompanies these entries yet.

## [0.1.0] - 2026-11-16

### Added

- Initial public source snapshot of the control plane: FastAPI backend, Next.js
  dashboard, Telegram bot source, six protocol container builds, database migrations,
  backend test suite and disposable test-stack tooling.
- `LICENSE` preserved verbatim from the source baseline; no additional licence terms.
- `SOURCE_MANIFEST.json` recording the source revision, output hashes and transform
  counts for the exported tree.
- `THIRD_PARTY_REVIEW.md` inventory aid for dependency, notice and protocol-image
  obligations.
- RunOnFlux/FluxCloud integration source, including application-specification
  generation, node discovery and health monitoring.
- `.env.example` with empty required values, and a test-only Compose stack that mounts
  no host data.

### Notes

- Snapshot only: no dependency install, migration, image build or protocol traffic was
  verified for this export.
- Rights, contribution provenance and credential-revocation questions remain open; see
  [SECURITY.md](SECURITY.md) and [THIRD_PARTY_REVIEW.md](THIRD_PARTY_REVIEW.md).

## Versioning policy

- While the project is experimental it uses `0.x` versions; any `0.x` release may
  include breaking changes.
- A version number describes a **public snapshot of this repository**, not the internal
  history it was derived from and not any deployed service.
- Changelog entries are added in the same pull request as the change they describe.
- Creating a Git tag or GitHub release is a deliberate maintainer action and is not
  implied by an entry in this file.
