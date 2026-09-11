# Partisan Baseline 4.0A — First empirical backtest

Mode: shadow research only. Public site unchanged.

## Reference result

The current reference model is **R4_faction**:

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

Remaining high-coverage residuals are strongly associated with candidate incumbency. A downstream diagnostic adding only a signed incumbent-candidate indicator (DPP incumbent +1; KMT incumbent -1; otherwise 0), with alpha selected inside the 2018 training fold, gives:

- 2022 MAE: **4.910 pp**
- High-reliability MAE: **4.038 pp**
- RMSE: **6.495 pp**

This is **not** promoted into Partisan Baseline. It is evidence that candidate effects must be estimated downstream.

The candidate-incumbency diagnostic materially reduces errors in, among others, Chiayi City, Yunlin, Taichung, New Taipei, Hsinchu County, Hualien and Taitung. It is less successful in a few cases such as Penghu, showing that incumbency is not a universal fixed bonus and should be regularized together with candidate history.

## Reliability weighting

The predeclared high-reliability cutoff remains `major-party coverage >= 0.80`. Stronger continuous down-weighting of low-coverage labels improved 2018 high-reliability leave-one-out error modestly, but this remains a challenger and is not promoted solely because of its 2022 score.

## Model decision

1. Keep **R4_faction** as the current structural reference model.
2. Do not treat low-major-party-coverage races as clean structural labels.
3. Keep incumbency, repeat-candidate history and candidate-specific prior performance in the downstream Candidate Effect model.
4. Keep 2006/2009/2010 data for persistence, faction and organization diagnostics rather than equal-weight target labels.
5. Retain rejected challengers in the research record to prevent result-shopping.
6. Keep `release_allowed = false`; no public-site promotion.
