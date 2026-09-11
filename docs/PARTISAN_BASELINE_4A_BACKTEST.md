# Partisan Baseline 4.0A — First empirical backtest

Mode: shadow research only. Public site unchanged.

## Reference result

The current structural reference model is **R4_faction**:

`previous_local_dpp2 + presidential_relative_lean + council_vote_advantage + council_independent_share + town_vote_advantage + town_independent_share + town_available + faction_propensity`

2022 structural two-party evaluation:

- MAE: **5.909 pp**
- RMSE: **7.368 pp**
- High-reliability MAE (`major-party coverage >= 0.80`): **5.547 pp**
- High-reliability RMSE: **7.031 pp**

Carry-forward previous-local benchmark:

- MAE: **6.315 pp**
- RMSE: **8.023 pp**

R4 therefore improves the overall structural MAE by **0.407 pp** relative to direct carry-forward.

## Ablation

| Model | 2022 MAE | RMSE | High-reliability MAE |
|---|---:|---:|---:|
| R0 carry-forward | 6.315 | 8.023 | 6.109 |
| R1 presidential relative lean | 6.485 | 7.939 | 6.195 |
| R2 + council organization | 6.321 | 7.842 | 6.044 |
| R3 + township organization | 6.147 | 7.544 | 5.692 |
| R4 + faction propensity | **5.909** | **7.368** | **5.547** |
| R5 + local trend challenger | 6.021 | 7.471 | 5.637 |
| R6 + organization-trend challenger | 6.051 | 7.896 | 5.978 |

Direct presidential-swing extrapolation and equal use of older target cycles were separately stress-tested and rejected: they increased 2022 error materially. Older cycles remain useful for persistence, faction and organization diagnostics, but are not treated as homogeneous target labels.

## Main failure modes

Low major-party coverage is not a clean measurement of KMT-DPP structure. Strong third-party or independent candidates can change the observed KMT/DPP ratio even if the underlying partisan structure changes little. Such races must therefore be down-weighted and evaluated separately.

The clearest example is 2022 Hsinchu City: the TPP candidate won 45.02% while KMT received 18.07%, so the observed DPP share among KMT+DPP votes becomes artificially high as a structural label. This is a candidate/third-party disruption problem rather than evidence of a sudden deep-green baseline.

## Candidate-effect handoff

Candidate-effect work is now implemented in a separate downstream module. The structural R4 prediction is frozen first; Candidate Effect 3.0 models only the log-odds residual around that baseline. Previous-winner status is not automatically treated as verified incumbency.

A strict residual-model ablation shows only modest incremental gains from repeat-candidate and previous-winner history. All candidate residual specifications choose very strong shrinkage, which argues against a universal fixed candidate or incumbency bonus.

The legacy direct candidate model remains complementary: on the same 19-county 2022 KMT-DPP two-party target it records MAE **5.666 pp**, better than R4's 5.909. Because the legacy and structural models have different biases, a stacking challenger was tested with its rule selected exclusively on 2018 county-out-of-fold predictions.

The 2018 OOF selection chooses a **90% R4 / 10% legacy blend on the logit scale**. Applied unchanged to the untouched 2022 holdout, it records:

- overall MAE: **5.416 pp**;
- RMSE: **6.842 pp**;
- high-reliability MAE: **4.960 pp**.

This is currently the best leakage-safe two-party result in the research branch, but it is **not** promoted into Partisan Baseline. It is a downstream candidate-layer challenger and requires validation on a second historical time cycle.

## Reliability weighting

The predeclared high-reliability cutoff remains `major-party coverage >= 0.80`. Stronger continuous down-weighting of low-coverage labels improves 2018 high-reliability leave-one-out error modestly as the coverage exponent rises, but this remains a challenger and is not promoted solely because of its 2022 score.

## Model decision

1. Keep **R4_faction** as the structural reference model.
2. Keep the OOF-selected 90/10 logit stack as a downstream challenger only.
3. Do not treat low-major-party-coverage races as clean structural labels.
4. Do not hard-code a universal incumbency bonus into Partisan Baseline.
5. Keep incumbency, repeat-candidate history and candidate-specific prior performance in Candidate Effect.
6. Keep 2006/2009/2010 data for persistence, faction and organization diagnostics and for constructing earlier historical folds.
7. Require a second historical time-cycle test before promoting any stack.
8. Keep `release_allowed = false`; no public-site promotion.
