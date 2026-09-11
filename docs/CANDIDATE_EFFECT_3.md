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

The Partisan Baseline 4.0A backtest shows that lagged council, township and faction information improves the 2022 structural two-party MAE, but important high-coverage residuals remain. A joint diagnostic using a signed incumbent indicator produced a large apparent gain, while the stricter two-stage test produced only a modest gain. Candidate effects therefore exist but are heterogeneous and must not be encoded as a universal incumbency bonus.

The legacy `fundamentals.py` contains useful candidate-history signals, but predicts the whole race directly. Candidate Effect 3.0 instead uses candidate information only to explain residuals around a frozen structural baseline.

## Features and ablation

All signals are signed from the DPP perspective. The predeclared sequence is:

- C0: frozen R4 structural baseline.
- C1: `repeat_candidate_signal`.
- C2: + `prior_winner_signal`.
- C3: + separately `verified_incumbency_signal`.
- C4: + `prior_candidate_residual_signal` (reference architecture).
- C5: + `previous_candidate_share_signal`, retained as a challenger because raw prior vote is structurally confounded.

`previous_winner` is not silently relabeled as verified incumbency. Verified incumbency must be supplied independently.

## Estimation

The implementation uses zero-intercept weighted ridge regression. A cycle-wide residual belongs to structural/election-environment modeling, not candidate quality. Feature columns are scaled but not centered, so zero retains the meaning "no observed candidate asymmetry".

Shrinkage is selected only inside the 2018 training cycle by leave-one-county-out validation over:

`0.3, 1, 3, 10, 30`

2018 structural labels are themselves county-out-of-fold R4 predictions; 2022 structural inputs are untouched time-holdout R4 predictions. The pipeline rejects in-sample structural labels.

## First empirical 2018 -> 2022 holdout

The automatically generated panel contains 16 training counties and 19 2022 holdout counties. All 35 structural rows passed the KMT/DPP matchup adapter. The full repository test suite and Candidate Effect research runner completed successfully in isolated CI.

| Specification | Selected alpha | 2022 MAE | RMSE | High-coverage MAE |
|---|---:|---:|---:|---:|
| C0 frozen R4 | — | 5.909 | 7.368 | 5.547 |
| C1 repeat candidate | 30 | 5.855 | 7.320 | 5.484 |
| C2 + previous winner | 30 | **5.800** | **7.281** | **5.412** |
| C3 + verified incumbency | 30 | 5.800 | 7.281 | 5.412 |
| C4 + prior candidate residual | 30 | 5.800 | 7.281 | 5.412 |
| C5 + previous-share challenger | 30 | **5.753** | **7.240** | **5.356** |

Relative to C0, C2 improves overall MAE by about 0.108 pp and high-coverage MAE by about 0.136 pp. C5 improves overall MAE by about 0.155 pp and high-coverage MAE by about 0.191 pp, but it remains a challenger rather than the reference model because previous candidate vote share mixes person-specific performance with the old election's structural environment.

Every fitted candidate specification selects the maximum predeclared shrinkage (`alpha=30`). This is substantive evidence that candidate-history effects are weakly identified with only one training cycle and should be strongly pooled toward zero.

The current panel has no audited variation in `verified_incumbency_signal` and no earlier-cycle estimate for `prior_candidate_residual_signal`; both are therefore explicitly reported as `no_training_variation`. C3 and C4 cannot yet improve on C2. This is a data limitation, not evidence that those concepts have zero effect.

## Interpretation

Exact-name repeat candidacy and previous-winner status add a small but reproducible amount of information beyond R4. The gain is much smaller than the earlier joint incumbency diagnostic, confirming that the large apparent incumbency effect was partly structural-model interaction rather than a portable fixed bonus.

For 2022, repeat/winner history modestly improves several KMT repeat-winner races such as New Taipei, Taichung, Yunlin and Chiayi City, but the adjustment is deliberately tiny under strong shrinkage. It can also worsen races such as Pingtung or Penghu, reinforcing the decision not to hard-code a large incumbency bonus.

## Third-party races

Candidate Effect 3.0 does not allocate TPP/independent/other vote share. Strong third-party races can contaminate the observed KMT/DPP ratio even when both major-party candidates are present. Such races remain down-weighted by major-party coverage and require a separate Third Party / Faction compositional model.

## Relationship to the legacy candidate model

`model/fundamentals.py` remains a challenger. It directly models candidate-centered log-ratio outcomes using previous candidate share, party history and previous-winner status. Candidate Effect 3.0 does not delete that model; the two approaches should ultimately be compared under the same leakage-safe historical holdout.

## Current decision

1. Keep R4 as the structural baseline.
2. Use C2 as the currently estimable conservative candidate-history adjustment; do not promote C5 solely because it has the lowest 2022 error.
3. Keep C4 as the intended architecture once verified incumbency and earlier candidate residuals have real training variation.
4. Do not encode a universal incumbency bonus.
5. Keep `release_allowed = false` and do not modify the public site.

## Remaining release gates

- add independently verified incumbency for historical races;
- generate earlier candidate-residual history so C4 has actual training variation;
- audit candidate aliases beyond exact-name matching;
- explicitly model third-party vote allocation;
- validate Candidate Effect over more than one historical training cycle;
- review public-site integration separately.
