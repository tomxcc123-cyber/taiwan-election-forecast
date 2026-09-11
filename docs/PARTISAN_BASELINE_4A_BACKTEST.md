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

Remaining high-coverage residuals are visibly associated with candidate incumbency. A **joint diagnostic** that allows the structural regression to use a signed incumbent-candidate indicator (DPP incumbent +1; KMT incumbent -1; otherwise 0) gives:

- 2022 MAE: **4.910 pp**
- High-reliability MAE: **4.038 pp**
- RMSE: **6.495 pp**

That result must not be interpreted as a validated fixed incumbency bonus, because the candidate term is allowed to interact with the structural regression during fitting.

A stricter **two-stage separation test** was therefore run: first produce leave-one-county-out R4 structural predictions for 2018; then fit only an incumbency coefficient to those out-of-fold residuals; finally apply that residual model to untouched 2022 R4 predictions. Internal 2018 CV chose strong shrinkage (`alpha=10`), leaving only a small incumbency coefficient. The strict two-stage 2022 result is:

- MAE: **5.792 pp**
- High-reliability MAE: **5.395 pp**
- RMSE: **7.271 pp**

This is only a modest improvement over R4. The correct conclusion is therefore not “add a fixed incumbency bonus,” but rather: **candidate effects are real, yet incumbency alone is too weak and heterogeneous to estimate reliably from one training cycle.** Candidate history, repeat-candidate performance, prior winner status and other candidate-level information must be estimated in the downstream Candidate Effect model.

The descriptive 2022 residual pattern remains informative: KMT incumbent-candidate races tend to have lower DPP residuals, while DPP incumbent-candidate races tend to have higher DPP residuals. Exceptions such as Penghu reinforce the need for shrinkage and candidate-specific history.

## Candidate Effect 3.0 handoff

Candidate-effect work now proceeds in a separate module. The structural R4 prediction is frozen first; Candidate Effect 3.0 then models only the log-odds residual around that baseline. Its initial feature channels are exact-name repeat-candidate status, previous-winner status, previously estimated candidate residual and separately verified incumbency. Previous-winner status is **not** automatically treated as incumbency.

This separation is intentional: a cycle-wide error belongs to structural/election-environment modeling, while a repeatable person-specific residual belongs to Candidate Effect. The candidate-effect model therefore uses a zero intercept and strong regularization, with shrinkage selected only inside the historical training cycle.

## Reliability weighting

The predeclared high-reliability cutoff remains `major-party coverage >= 0.80`. Stronger continuous down-weighting of low-coverage labels improves 2018 high-reliability leave-one-out error modestly as the coverage exponent rises, but this remains a challenger and is not promoted solely because of its 2022 score.

## Model decision

1. Keep **R4_faction** as the current structural reference model.
2. Do not treat low-major-party-coverage races as clean structural labels.
3. Do not hard-code a universal incumbency bonus into Partisan Baseline.
4. Keep incumbency, repeat-candidate history and candidate-specific prior performance in the downstream Candidate Effect model.
5. Keep 2006/2009/2010 data for persistence, faction and organization diagnostics rather than equal-weight target labels.
6. Retain rejected challengers in the research record to prevent result-shopping.
7. Keep `release_allowed = false`; no public-site promotion.
