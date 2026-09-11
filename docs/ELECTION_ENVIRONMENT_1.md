# Election Environment 1.0 — cycle-level local-election shock

Status: shadow research only. Public site unchanged.

## Why this layer now exists

Partisan Baseline 4.0A improves the 2018→2022 structural holdout, but fails badly on the earlier 2014→2018 cycle. The same R4 specification gives:

| Holdout | R4 MAE | Carry-forward MAE |
|---|---:|---:|
| 2014→2018 | **12.312 pp** | **11.677 pp** |
| 2018→2022 rebuilt | **5.982 pp** | **6.315 pp** |

The rebuilt 2022 R4 predictions differ from the previously frozen R4 predictions by only 0.455 pp on average (maximum 1.317 pp), so the earlier-cycle failure is not an implementation mismatch large enough to explain the result. R4 is genuinely cycle-sensitive.

This motivates a separate cycle-level term rather than forcing permanent partisan structure, candidate effects or presidential swing to absorb every national local-election wave.

## Statistical decomposition

For county `c` in local-election cycle `t`:

`logit(observed_dpp2_ct) = logit(structural_baseline_ct) + environment_shock_t + county_residual_ct`

The realized historical common shock is the reliability-weighted mean of:

`logit(observed_dpp2) - logit(structural_baseline_dpp2)`

It is an **outcome-dependent diagnostic**. It is not a legal same-cycle predictive feature.

## Historical diagnostic

### 2018

The 2014-trained R4 model systematically overpredicts DPP two-party performance in 2018.

- realized common shock: **−0.4757 logit** (`actual - structural`), therefore KMT-positive;
- R4 share-space mean error: about **+11.19 pp DPP**;
- within-cycle residual SD after removing the common shock: **0.3418 logit**;
- weighted squared-error fraction explained by one common shock: **65.96%**;
- R4 raw MAE: **12.312 pp**;
- diagnostic oracle MAE if the realized common shock had somehow been known: **7.207 pp**.

The oracle correction is not a forecast. Its purpose is to show that most of the 2018 failure has a common-direction component rather than being 16 unrelated county failures.

### 2022

The corresponding rebuilt 2018-trained R4 result is much closer to neutral:

- realized common shock: **−0.0498 logit**;
- within-cycle residual SD: **0.2903 logit**;
- squared-error fraction explained by a common shock: **2.86%**;
- R4 MAE: **5.982 pp**;
- diagnostic oracle MAE after removing the realized common shock: **5.750 pp**.

Thus 2018 behaves like a strong national/local election environment shock; 2022 does not.

## Historical uncertainty scale

With only two comparable holdout cycles, no stable parametric environment model can be claimed. As a descriptive challenger only, the zero-centered RMS of the two realized logit shocks is:

`environment_rms_logit = 0.3382`

At an exactly 50/50 structural race, a ±0.338 logit movement corresponds roughly to ±8.4 percentage points in two-party share. This is **not** a calibrated 68% interval; two cycles are far too few for that claim.

## Forecast policy

Until an ex-ante Election Environment predictor passes multi-cycle validation:

1. Future environment point mean is fixed at **0**.
2. Historical realized shocks may **not** be copied into a future point forecast.
3. Historical environment variation may be used only as a research challenger for widening simulation uncertainty.
4. Polls remain downstream in the Polling layer and cannot be used to retroactively redefine the structural baseline.
5. Candidate effects remain in Candidate Effect; strong TPP/independent vote allocation remains in Third Party/Faction.

This prevents a common failure mode: observing the 2018 KMT wave, inventing a hand-set 'midterm −X' constant, and then overcorrecting 2022 or 2026.

## What should eventually predict the environment?

Possible ex-ante predictors can be studied, but none is promoted yet:

- governing-party midterm status;
- national executive approval / dissatisfaction measured before the election;
- economy and inflation/unemployment changes;
- national party identification or party-list trend;
- aggregate local-election generic ballot / nationalized polling signal;
- major national political shocks.

Each candidate variable must be available before the target election and validated on historical folds. Direct presidential-election swing has already been tested and rejected as a simple linear predictor of local-election swing.

## Architecture decision

The model decomposition is now:

`Stable Partisan Baseline`

`+ Election Environment`

`+ Candidate Effect`

`+ Third Party / Faction allocation`

`+ Polling calibration`

`+ Turnout and Monte Carlo simulation`

Partisan Baseline should be interpreted as structural geography, not as a promise that the actual local election will reproduce that structure in every national political environment.

## Release gate

`release_allowed = false`.

Election Environment cannot shift the 2026 point forecast until an ex-ante model demonstrates stable incremental value on more than one historical time fold. The current `0.3382` logit scale is diagnostic uncertainty only.
