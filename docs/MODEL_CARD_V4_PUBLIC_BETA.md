# HB-TLEF v4.0 Public Beta 1 — Model Card

Status: **Public Beta; public research release deployed on 2026-09-11.**

This document describes the frozen HB-TLEF v4.0 research core now published for public inspection and historical validation. The live 2026 website forecast pipeline has not yet been migrated to this core because the 2026 structural feature layer is still being integrated. Accordingly, current live 2026 point estimates must not be described as v4 outputs. This release must not be described as a stable or fully calibrated forecast model.

## 1. Forecast object

The model estimates county/city executive candidate vote shares and winner probabilities. It separates four concepts that older versions mixed together:

1. KMT–DPP structural partisanship.
2. Non-major-party / independent vote mass.
3. Candidate-specific allocation.
4. Election-wide and campaign uncertainty.

Polls are downstream evidence. They are not legal inputs to the Partisan Baseline layer. Blue–white vote transfer is also downstream scenario logic rather than a baseline assumption.

## 2. Frozen architecture

### 2.1 Two-party structural baseline

The structural target is DPP share among KMT+DPP votes rather than raw three-bloc vote share. This prevents a strong independent or third-party candidate from being interpreted as permanent disappearance of KMT/DPP partisan support.

The v4 beta combines the Partisan Baseline 4.0A estimate and the older direct fundamentals estimate in logit space. The weight is frozen at 0.90 for R4 and 0.10 for the legacy estimate. This weight was selected on the 2018 historical selection cycle and is not tuned on 2022 outcomes.

### 2.2 Non-major vote mass

The non-major component uses the T3 roster-type regularized model with alpha=0.3. Inputs are lagged non-major vote share, council independent share, township-mayor independent share/availability, faction propensity, non-major candidate count, TPP presence, and independent/minor-party candidate counts.

Its point estimate is blended in share space with the previous local-election non-major share: 70% model, 30% carry-forward. This blend was selected on 2018 only.

This component is deliberately described as **non-major mass**, not as a single ideological “THIRD” bloc. TPP, independents and local factions remain substantively distinct and should be separated further when 2020/2024 county-level party-list data are added.

### 2.3 Reliability gate and fallback

The fully compositional model is not trusted mechanically in every county. A reliability score is computed as:

`score = total-variation disagreement between compositional and direct candidate models + absolute non-major-mass jump from the previous election`

The frozen threshold is `0.075`, selected on 2018. Inside the validated envelope the compositional correction is used. Outside it, the forecast falls back to the direct candidate fundamentals model. The purpose is not to hide difficult races; it is to prevent unstable third-party/faction extrapolation from overwriting a better-supported conservative prior.

### 2.4 Winner probabilities

Historical validation uses Monte Carlo perturbations on log point shares. The frozen Gaussian scale is `sigma = 0.95`, selected on 2018 multiclass Brier score, with 12,000 validation draws per race. These probabilities are **research probabilities**, not yet claimed to be fully calibrated election probabilities.

## 3. Historical validation

The chronological candidate chain covers all 22 counties/cities in 2014, 2018 and 2022. The predecessor layer for 2014 consists of the actual 2009 county/city and 2010 five-municipality elections; these dates are retained rather than relabeled.

The 2018 cycle is used for architecture parameter selection. The 2022 cycle is the main later time holdout for the frozen numeric parameters. On 2022, the selective v4 beta produces:

| Metric | Legacy comparator | v4 Public Beta |
| --- | ---: | ---: |
| Race-balanced candidate-share MAE | 6.085 pp | **5.981 pp** |
| Winner accuracy | 14/22 (63.6%) | **14/22 (63.6%)** |
| Top-two margin MAE | 11.686 pp | **11.277 pp** |
| Multiclass Brier score | 0.5026 | **0.5007** |
| Probability argmax accuracy | — | 15/22 (68.2%) |

All current Public Beta release gates pass: point-share MAE is no worse than legacy, margin MAE improves, point winner accuracy does not deteriorate, Brier score improves, chronological ordering is valid, and fallback behavior is active rather than theoretical.

The result should still be interpreted conservatively. The point-winner score remains 14/22, below the previously discussed 15/22 research target.

## 4. Why this is Public Beta rather than Stable

The model is eligible for a transparent Public Beta because it improves the principal 2022 error metrics without sacrificing point-winner accuracy and because it has an explicit failure-safe fallback. It is not eligible for Stable for four reasons.

First, 14/22 point-winner accuracy is below the predeclared 15/22 target. Second, although all RC3 numeric choices were selected on 2018, the decision to introduce a fallback architecture followed inspection of RC2's 2022 failure pattern; therefore 2022 is not a pristine architecture-blind test. Third, 2009/2010 counts have been transcribed and cross-checked but are not yet backed by raw-workbook hash verification (`source_verified=false`). Fourth, probability calibration evidence is still thin across election cycles.

These limitations must be displayed with any public beta release. They are not grounds to discard the model; they define the boundary of what can be claimed.

## 5. Data provenance and leakage policy

Historical 2014/2018/2022 local executive rows use audited CEC-based records in the repository. Older 2009/2010 rows pass internal arithmetic and roster checks but retain an explicit provenance warning until raw-source verification is completed.

The baseline does not ingest current 2026 polls, current campaign events, future outcomes, or ad-hoc candidate ratings. Polling is a separate downstream likelihood. Historical poll research may estimate poll-error parameters but cannot rewrite the structural baseline. Same-cycle realized election-environment shocks are diagnostics only and cannot shift a future point forecast unless an ex-ante environment predictor passes separate validation.

## 6. Public presentation rules

The v4 research core, release manifest and model card are now public. Until the 2026 structural feature rows and product adapter are completed, the public website must explicitly distinguish the v4 research release from the existing live 2026 forecast engine.

A future v4-powered 2026 forecast page should show the exact model version, generation time, candidate set timestamp, point estimates, uncertainty interval/probability, and whether a county used compositional mode or fallback mode. It must say `Public Beta` and must not use language such as “calibrated probability” or “stable model” until the stable gates pass.

The site should expose enough information for a reader to distinguish three things: structural baseline, candidate/poll updates, and final simulated forecast. This separation is essential for interpretability and for later backtesting.

## 7. Stable promotion requirements

Stable promotion is blocked until, at minimum, the following are satisfied: point-winner accuracy reaches the predeclared 15/22 target or an equivalent independently preregistered criterion; a genuinely architecture-independent historical or future validation surface is available; 2009/2010 provenance is raw-source verified; and probability calibration is demonstrated across more than one usable election cycle.

Adding county-level 2020 and 2024 party-list votes, especially TPP support, is a high-priority structural improvement. It should be introduced as a new feature version and revalidated chronologically rather than silently altering this frozen beta.

## 8. Reproducibility

The machine-readable release definition is `model/releases/v4-public-beta.1.json`. CI runs the full research validation and then `scripts/audit_public_beta_release.py`. A build may be called Public Beta only when that audit reports `public_beta_allowed=true`. `stable_allowed` remains false in this release.
