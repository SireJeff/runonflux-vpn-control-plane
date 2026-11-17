# Third-party provenance review

This file is an inventory aid. It is **not** a substitute for license texts, and it is
**not** a conclusion that every item in this repository can be offered under one root
license. Where an obligation is unverified, that is stated rather than assumed.

Keep every existing license, notice and copyright text intact. Do not claim that this
review, a clean secret scan, or publication itself grants rights that remain unresolved.

## How to use this document

1. Identify the artefacts you intend to distribute (source archive, container images,
   built dashboard bundle, vendored extracts).
2. For each row below, confirm the obligation against the actual pinned versions.
3. Record the outcome — resolved, or explicitly accepted as a known gap — before
   redistribution you intend to rely on.

## Root licence

- `LICENSE` is copied verbatim from the source baseline. It contains an existing
  dedication with custom wording.
- No additional licence, CLA or proprietary exception has been applied by this
  repository.
- Ownership, prior grants and contribution provenance for the underlying work are not
  established here. This is the largest open question in this inventory.

## Python backend

- `worker_api/requirements.txt` retains original package versions. The distributable
  dependency inventory and the required notice set must be resolved from the actually
  installed versions, not from this file.
- Transitive dependencies may carry obligations distinct from the direct ones
  (copyleft, notice, or source-availability requirements).
- No dependency licence scan has been performed for this snapshot.

## Dashboard

- `admin-dashboard/package.json` and `package-lock.json` retain original versions and
  lockfile integrity data.
- The UI primitives follow the shadcn/ui, Radix UI and Lucide ecosystems. Generated or
  copied component source requires attribution verification that goes beyond the
  package manifests; per-project licence texts for those ecosystems are included under
  [LICENSES/](LICENSES/) as aids only.
- The bundled dashboard output contains transformed and minified third-party code whose
  notices must be resolved for any redistributed build.

## Telegram bot

- `telegram_bot/requirements.txt` retains original versions.
- Persian and English localisation strings are part of this codebase; review any text
  that originated elsewhere before redistribution.

## Protocol images

- `integrations/*/Dockerfile` build on upstream protocol engines and inherit base-image
  packages (including Squid, OpenSSH and Xray-related software) with separate
  obligations.
- Image digests, notices and source-availability requirements must be reviewed before
  redistributing any built image. Build files alone do not carry those notices.
- Shared bootstrap helpers in `integrations/base/` are part of this repository; the
  engines they launch are not.

## Webfonts, icons and other assets

- An unverified binary favicon and an optional landing page were intentionally omitted
  from this snapshot, so their rights are not represented here and must not be assumed
  to be cleared.
- The dashboard uses system font stacks and icon components from the ecosystems listed
  above. Add webfont files only with provenance recorded.

## What is deliberately not asserted

- That one licence covers the whole repository.
- That the included inventory is complete.
- That any previously published or deployed artefact is unaffected by these
  obligations.
- That a clean secret scan has any bearing on licensing.
