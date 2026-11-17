# License inventory aids

This directory holds third-party licence texts and attribution notes that are useful
when resolving obligations for this repository. It is deliberately minimal.

| File | Purpose |
| --- | --- |
| [`APACHE-2.0.txt`](APACHE-2.0.txt) | Apache License 2.0 text, referenced by upstream components |
| [`PROSOPO-ATTRIBUTION.txt`](PROSOPO-ATTRIBUTION.txt) | Attribution note for an upstream implementation referenced by the platform integration |
| [`SHADCN-UI.txt`](SHADCN-UI.txt) | MIT licence text for the shadcn/ui component ecosystem used by the dashboard |

## This is not a complete notice set

- These files are **aids**, not a resolved notice bundle for a redistributable release.
- No dependency-licence scan has been run for this snapshot, so transitive obligations
  are not represented here.
- Protocol container images additionally inherit their base-image and engine
  obligations, which are not covered by these files.
- The root [`LICENSE`](../LICENSE) is preserved verbatim from the source baseline, and
  the overall rights position of this repository is unresolved.

See [`THIRD_PARTY_REVIEW.md`](../THIRD_PARTY_REVIEW.md) for the component-by-component
inventory and the obligations that still require verification before redistribution.
