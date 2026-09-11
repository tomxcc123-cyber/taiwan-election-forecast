# Candidate Effect 3.0 — downstream residual model

Status: shadow research only. Public site unchanged.

## Objective

Candidate Effect 3.0 estimates the part of a KMT-DPP local-election result that is not explained by the frozen Partisan Baseline 4 structural estimate.

For county `c` and election `t`:

`candidate_residual = logit(observed_dpp_two_party) - logit(structural_baseline_dpp_two_party)`

The final two-party candidate-adjusted estimate is:

`logit(adjusted_dpp_two_party) = logit(structural_baseline) + predicted_candidate_residual`

The structural model is never refit with candidate features.

## Why a separate layer is necessary

The Partisan Baseline 4.0A backtest shows that lagged council, township and faction information improves the 2022 structural two-party MAE, but important high-coverage residuals remain. A joint diagnostic using a signed incumbent indicator produced a large apparent gain, while the stricter two-stage test produced only a modest gain. This means candidate effects exist but are heterogeneous and must not be encoded as a universal incumbency bonus.

The current candidate-level `fundamentals.py` already contains useful historical signals — previous candidate share, previous listed winner, exact-name continuity and named-party history — but it predicts the whole race directly. Candidate Effect 3.0 instead uses such signals only to explain residuals around the frozen structural baseline.

## Reference features

The first residual model reserves four pre-election feature channels:

- `repeat_candidate_signal`: DPP repeat candidate minus KMT repeat candidate.
- `prior_winner_signal`: DPP repeat winner minus KMT repeat winner. This is not automatically called incumbency.
- `prior_candidate_residual_signal`: signed prior candidate over/under-performance relative to the prior frozen structural baseline.
- `verified_incumbency_signal`: +1 for a verified DPP incumbent candidate, -1 for a verified KMT incumbent candidate, 0 otherwise.

All features are signed from the DPP perspective. Positive values should, other things equal, move DPP two-party share upward; negative values move it downward.

## Estimation

The first implementation uses zero-intercept weighted ridge regression.

The intercept is fixed at zero because a nationwide cycle-wide residual should be handled by the structural/election-environment layer, not silently relabeled as candidate quality.

Feature columns are scaled but not centered. Therefore feature value zero retains the semantic meaning "no observed candidate asymmetry".

Shrinkage is selected only inside the historical training cycle with leave-one-county-out validation over the predeclared grid:

`0.3, 1, 3, 10, 30`

The later election cycle is evaluated once and is not used to tune alpha.

## Training protocol

Initial protocol:

1. Build leakage-safe Partisan Baseline predictions for the training cycle using only earlier data.
2. Generate out-of-fold structural predictions for each training county.
3. Compute candidate residual labels from those frozen structural predictions.
4. Build candidate features using only candidate information available before that election.
5. Select candidate-effect shrinkage inside the training cycle.
6. Refit Candidate Effect on the full training cycle residual panel.
7. Apply it to the untouched later-cycle structural predictions.
8. Compare structural-only and candidate-adjusted MAE/RMSE, including the high-major-party-coverage subset.

For the first full experiment, 2018 is the candidate-effect training cycle and 2022 is the untouched holdout.

## Third-party races

Candidate Effect 3.0 does not allocate TPP/independent/other vote share. Strong third-party races can contaminate the observed KMT-DPP ratio, so low-major-party-coverage races remain down-weighted and are evaluated separately. A future Third Party / Faction model will handle the full compositional vote allocation.

## Relationship to the legacy candidate model

`model/fundamentals.py` remains a useful challenger. It directly models candidate-centered log-ratio outcomes using previous candidate share, party history and previous winner status. Candidate Effect 3.0 does not delete that model; instead, the two approaches should be compared under the same 2018 -> 2022 holdout.

Promotion rule: candidate residual modeling must beat the frozen R4 structural baseline on the untouched holdout without relying on target-cycle tuning. A single descriptive incumbency effect is insufficient for promotion.

## Release gate

`release_allowed = false` until:

- the canonical candidate-effect panel is committed with provenance;
- 2018 out-of-fold structural labels are reproducible;
- candidate identity/continuity checks are audited;
- the 2022 holdout shows stable incremental gain;
- third-party contamination is handled explicitly;
- public-site integration is reviewed separately.
