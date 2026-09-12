# HB-TLEF v4.1 Public Beta 2 Release Notes

Release date: 2026-09-12

## What changed

- Added a production `Fragmentation Poll Gate` for strong third-party / independent contests.
- The gate is intentionally narrow: only already-accepted, full-field TVBS polls can hard-trigger it.
- Frozen trigger: non-KMT/DPP candidates must account for at least 40% of decided named-candidate support.
- On trigger, the county posterior draw cloud is recentered to the full poll vector in centered-log-ratio space while preserving the draw shape.
- Partial-ballot polls, other pollsters, weaker fragmentation and roster mismatches remain on the existing joint Gaussian polling likelihood.
- Added an explicit v4.1 release manifest and governance audit.
- Added unit tests covering trigger, non-trigger and exact draw normalization behavior.
- The public site now exposes v4.1 model card and release manifest.

## Validation status

The old selective v4.0 RC3 remains the confirmatory 2022 reference:

- race-balanced MAE: 5.981pp
- winner direction: 14/22

The fragmentation-v3 2022 development diagnostic is:

- race-balanced MAE: 4.979pp
- winner direction: 16/22
- Hsinchu City winner corrected to Kao Hung-an
- Miaoli County winner corrected to Chung Tung-chin after an explicit audited glyph repair in the historical TVBS record

The 4.979pp result is **not** a pristine confirmatory holdout because the hard-fragmentation architecture was proposed after earlier 2022 challenger errors were inspected.

## Release classification

Public Beta: allowed.

Stable: blocked pending independent-cycle evidence and multi-cycle probability calibration.
