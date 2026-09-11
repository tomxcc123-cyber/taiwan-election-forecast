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

All signals are signed from the DPP perspective. The sequence currently tested is:

- C0: frozen R4 structural baseline.
- C1: `repeat_candidate_signal`.
- C2: + `prior_winner_signal`.
- C3: + separately `verified_incumbency_signal`.
- C4: + `prior_candidate_residual_signal` (clean reference architecture).
- C5: + `previous_candidate_share_signal`, challenger because raw prior vote is structurally confounded.
- C6: + `previous_party_pool_signal`, legacy-inspired challenger.
- C7: + both previous candidate share and previous party pool, legacy-hybrid challenger.

`previous_winner` is not silently relabeled as verified incumbency. Verified incumbency must be supplied independently.

## Estimation

The implementation uses zero-intercept weighted ridge regression. A cycle-wide residual belongs to structural/election-environment modeling, not candidate quality. Feature columns are scaled but not centered, so zero retains the meaning "no observed candidate asymmetry".

Shrinkage is selected only inside the 2018 training cycle by leave-one-county-out validation over:

`0.3, 1, 3, 10, 30`

2018 structural labels are themselves county-out-of-fold R4 predictions; 2022 structural inputs are untouched time-holdout R4 predictions. The pipeline rejects in-sample structural labels.

## First empirical 2018 -> 2022 holdout

The automatically generated panel contains 16 training counties and 19 2022 holdout counties. All 35 structural rows passed the KMT/DPP matchup adapter. The full repository test suite and Candidate Effect research runner complete successfully in isolated CI.

| Specification | Selected alpha | 2022 MAE | RMSE | High-coverage MAE |
|---|---:|---:|---:|---:|
| C0 frozen R4 | — | 5.909 | 7.368 | 5.547 |
| C1 repeat candidate | 30 | 5.855 | 7.320 | 5.484 |
| C2 + previous winner | 30 | 5.800 | 7.281 | 5.412 |
| C3 + verified incumbency | 30 | 5.800 | 7.281 | 5.412 |
| C4 + prior candidate residual | 30 | 5.800 | 7.281 | 5.412 |
| C5 + previous-share challenger | 30 | 5.753 | 7.240 | 5.356 |
| C6 + previous party-pool challenger | 30 | 5.787 | 7.271 | 5.401 |
| C7 legacy-hybrid challenger | 30 | 5.741 | 7.230 | 5.346 |

Every fitted candidate specification selects the maximum predeclared shrinkage (`alpha=30`). This is substantive evidence that candidate-history effects are weakly identified with only one training cycle and should be strongly pooled toward zero.

The current panel has no audited variation in `verified_incumbency_signal` and no earlier-cycle estimate for `prior_candidate_residual_signal`; both are therefore explicitly reported as `no_training_variation`. C3 and C4 cannot yet improve on C2. This is a data limitation, not evidence that those concepts have zero effect.

## Fair comparison with the legacy direct candidate model

The legacy model and Candidate Effect models are evaluated on the exact same 19 counties and the same target: DPP share among DPP+KMT votes. Legacy full-race probabilities are renormalized over exactly one DPP and one KMT candidate before scoring.

| Model | 2022 MAE | RMSE | Bias | High-coverage MAE |
|---|---:|---:|---:|---:|
| R4 frozen structural | 5.909 | 7.368 | +0.996 | 5.547 |
| C2 residual | 5.800 | 7.281 | +0.920 | 5.412 |
| C7 residual hybrid | 5.741 | 7.230 | +0.882 | 5.346 |
| Legacy `fundamentals.py` direct | **5.666** | **6.586** | -1.250 | **5.242** |

The legacy direct model therefore remains a serious challenger. Its advantage is not reproduced simply by adding raw previous candidate share and prior party-pool signals to the zero-intercept residual model. It appears to capture useful candidate-history interactions that C4 does not yet identify.

## OOF stacking challenger

Because R4 and the legacy direct model have different biases, a stacking experiment was added. The blend rule is selected only on 2018 county-out-of-fold predictions; no 2022 label is used to choose either the blending space or the weight.

Predeclared search:

- blending spaces: share and logit;
- legacy weight: 0.00 to 1.00 in 0.05 increments;
- selection criterion: 2018 county-OOF two-party MAE.

The 2018 selection chooses:

- `mode = logit`;
- `legacy_weight = 0.10`;
- equivalently, a 90% R4 / 10% legacy blend on the logit scale.

Untouched 2022 holdout:

| Model | MAE | RMSE | Bias | High-coverage MAE |
|---|---:|---:|---:|---:|
| R4 | 5.909 | 7.368 | +0.996 | 5.547 |
| Legacy direct | 5.666 | 6.586 | -1.250 | 5.242 |
| **OOF-selected stack** | **5.416** | 6.842 | +0.763 | **4.960** |

This is the best leakage-safe two-party MAE currently observed in the research branch. It is still a challenger rather than a promoted reference model because the stacking rule has only one historical selection cycle. A second time-cycle validation is required before promotion.

The next validation fold is explicitly defined as: construct a pre-2014 structural/candidate information set from the user-supplied 2009/2010 local executive, council and township data plus the 2012 presidential anchor; generate 2014 county-OOF structural and direct-candidate predictions; choose a blend using only that 2014 OOF fold; then apply it once to 2018. The 2009/2010 source material has been ingested offline, but its canonical repository import is still a release gate.

The stack does not solve third-party contamination. Hsinchu City remains a major failure because a strong TPP candidate changes the observed KMT/DPP ratio; that requires a separate compositional Third Party / Faction model.

## Interpretation

Exact-name repeat candidacy and previous-winner status add a small but reproducible amount of information beyond R4. The gain is much smaller than the earlier joint incumbency diagnostic, confirming that the large apparent incumbency effect was partly structural-model interaction rather than a portable fixed bonus.

The legacy model has useful complementary information, but its historical behavior is unstable: in 2018 county-OOF selection, a full legacy weight performs very poorly, while a small 10% contribution improves R4. This instability is precisely why the 2022 performance of the legacy model cannot by itself justify replacing the structural-plus-residual architecture.

## Third-party races

Candidate Effect 3.0 does not allocate TPP/independent/other vote share. Strong third-party races can contaminate the observed KMT/DPP ratio even when both major-party candidates are present. Such races remain down-weighted by major-party coverage and require a separate Third Party / Faction compositional model.

## Current decision

1. Keep R4 as the structural reference baseline.
2. Keep C4 as the clean intended Candidate Effect architecture, while acknowledging that two feature channels still lack training variation.
3. Keep legacy `fundamentals.py` as a strong direct-candidate challenger rather than deleting it.
4. Treat the 90% R4 / 10% legacy logit stack as the current best two-party challenger, not as a released model.
5. Require a second historical time-cycle validation before any stacking promotion.
6. Do not encode a universal incumbency bonus.
7. Keep `release_allowed = false` and do not modify the public site.

## Remaining release gates

- import the audited 2009/2010 aggregate and candidate-history inputs canonically into the repository;
- validate stacking on the 2014 -> 2018 historical time cycle;
- add independently verified incumbency for historical races;
- generate earlier candidate-residual history so C4 has actual training variation;
- audit candidate aliases beyond exact-name matching;
- explicitly model third-party vote allocation;
- review public-site integration separately.
