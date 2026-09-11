# Partisan Baseline 4.0A

Status: shadow research only. This work does not modify `site/` and must not be treated as a public 2026 forecast.

## Purpose

Estimate the latent KMT-DPP structural baseline separately from candidate, polling, coalition, turnout, and campaign effects.

The main target is:

`DPP2 = DPP votes / (DPP votes + KMT votes)`

and the fitted model works on `logit(DPP2)`.

## Data timing rule

Every input must have been available before the election being predicted. Same-cycle council or township results are forbidden in historical backtests.

Examples:

- 2014 target: use data available through 2010 local elections plus the 2012 presidential election.
- 2018 target: use data available through 2014 local elections plus the 2016 presidential election.
- 2022 target: use data available through 2018 local elections plus the 2020 presidential election.
- 2026 target: use data available through 2022 local elections plus the 2024 presidential election.

`model.baseline_data.assert_available_before()` is the hard leakage gate.

## Observation reliability

A local executive result is treated as a noisy measurement of latent partisanship. Its predeclared information weight is:

`source confidence × boundary confidence × party-label reliability × major-party coverage^gamma`

where major-party coverage is `(KMT + DPP votes) / valid votes`.

This prevents strongly independent/factional races from having the same influence as clean KMT-DPP contests.

## Ablation plan

- B0: previous local election only.
- B1: multi-cycle local level and structural trend.
- B2: B1 plus presidential anchor and relative national lean.
- B4: B2 plus council organization variables.
- B5: B4 plus township grassroots variables.
- B6: reliability weighting is enabled through each row's `information_weight`.
- B7: B5 plus historical faction propensity.
- B8: full hierarchical partial pooling is deferred until B0-B7 demonstrate out-of-sample value.

The experiment is evaluated using rolling time holdouts. The intended folds are 2014, 2018, and 2022 where sufficient prior data exist.

## Required processed county-panel fields

Each row represents one county and one target election year. Required modeling fields include:

- `county_id`
- `target_year`
- `target_dpp2`
- `information_weight`
- `party_label_reliability`
- `previous_local_dpp2`
- `historical_local_level`
- `presidential_anchor_dpp2`
- `presidential_relative_lean`
- `council_vote_advantage`
- `council_seat_advantage`
- `council_nomination_advantage`
- `council_persistence_advantage`
- `town_control_advantage`
- `town_vote_advantage`
- `town_persistence_advantage`
- `town_independent_share`
- `structural_trend`
- `faction_propensity`

Derived features must be rebuilt separately for each historical `as_of` date. A panel constructed with future cycles and then filtered by target year is not acceptable.

## Separation from the candidate model

The existing `model/fundamentals.py` remains the candidate-level research model. Partisan Baseline 4 does not replace it.

The intended downstream decomposition is:

`Partisan baseline + candidate effect + polling + turnout/simulation -> final forecast`

Third-party and independent/faction dynamics are not collapsed into the KMT-DPP latent baseline.
