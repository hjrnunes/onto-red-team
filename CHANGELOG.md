# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Fixed

- **WeightedMergeStrategy: per-domain distance normalization + dual threshold** — Candidates are
  now z-score normalized per domain before merging, making distances comparable across ontology
  collections with different embedding distributions (e.g. CSO plain English vs OBO technical
  jargon). A dual threshold rejects candidates that fail either a raw distance ceiling (0.6) or a
  z-score threshold (1.0 std above domain mean). Applied to both the domain-selected quota loop and
  the always-included pool. Fixes three gen4 regressions caused by the per-domain search
  introduction:
  - FIBO domain contamination in healthcare/RDaSH (FIBO 1.4% → 13.9% of axis samples)
  - CSO harm axis explosion in banking (12 → 48 CSO harm samples, 4x increase)
  - Empty prompts from incoherent axis combinations (7 null prompts in SWB Gemma 3)

  See `docs/anchor-search-mechanics.md` for full analysis.
