# Forecast architecture after Partisan Baseline 4.0A

Status: research architecture. Public site unchanged.

The historical experiments now support a layered model rather than a single fundamentals regression.

## Layer 1 — Stable Partisan Baseline

Purpose: estimate persistent KMT-DPP geographic structure from lagged local executive results, presidential relative lean, council organization, township organization and faction propensity.

Current research reference: `R4_faction`.

This layer is structural. It is not expected to absorb national local-election waves, candidate-specific quality or third-party vote transfers.

## Layer 2 — Election Environment

Purpose: represent the common cycle-level shock that can move many counties in the same direction.

Empirical motivation: one common logit shock explains about 66% of R4's weighted squared error in the 2018 holdout, but only about 3% in 2022.

Current policy: future point mean zero. Historical shock scale may be used only as an uncertainty challenger until an ex-ante environment predictor passes multiple historical folds.

## Layer 3 — Candidate Effect

Purpose: estimate candidate-specific over/under-performance around the frozen structural baseline.

Current clean architecture: Candidate Effect C4, based on repeat candidate, previous winner, verified incumbency and prior candidate residual signals under strong regularization. Some channels still lack historical training variation.

Legacy direct candidate fundamentals remains a challenger. A 90% R4 / 10% legacy logit stack selected exclusively from 2018 county-OOF predictions records 2022 two-party MAE 5.416 pp, but is not promoted until another time-cycle validation is possible.

## Layer 4 — Third Party / Faction

Purpose: model TPP, independents and factional candidates as compositional vote allocation, rather than collapsing them into a single THIRD bloc or treating the observed KMT/DPP ratio as uncontaminated.

This layer is required for cases such as Hsinchu City 2022, Taipei 2014/2018/2022, Miaoli and offshore-island elections.

## Layer 5 — Polling

Purpose: update the pre-election distribution using eligible polls, preserving undecided voters, pollster/source uncertainty, matchup identity and temporal cutoffs.

Historical TVBS poll data remains outside the Partisan Baseline and Candidate Effect training layers.

## Layer 6 — Turnout and simulation

Purpose: combine structural, environment, candidate, third-party and polling uncertainty into vote shares, win probabilities and scenario simulations.

The common Election Environment draw should be correlated across counties within each Monte Carlo draw; it must not be sampled independently for every county.

## Core decomposition

In conceptual log-odds form for the KMT-DPP component:

`local_two_party = structural_baseline + common_environment + candidate_effect + local_noise`

The full vote composition is then produced by the Third Party / Faction layer before polling and turnout calibration.

## Release policy

No research layer may update the public site automatically. `release_allowed=false` remains mandatory until multi-cycle validation, uncertainty calibration and third-party allocation are completed.
