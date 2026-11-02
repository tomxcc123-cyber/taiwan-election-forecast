"""Chronological Third Party (T3) vote-pool diagnostic; never a forecast tuner.

T3 is a non-KMT/DPP county vote-mass predictor. The 2014 cycle trains
2018; 2014+2018 train 2022. Model parameters/specifications have been
inspected during prior development, so 2022 is *chronological* but NOT a
project-wide pristine holdout. All newer hypotheses are shadow-only.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from model.third_party import fit as fit_t3, predict as predict_t3
from model.nonmajor_hurdle import fit as fit_hurdle, predict_share as predict_hurdle
from model.v4_product import T3_ALPHA, T3_CARRY_WEIGHT, T3_FEATURES, T3_MODEL_WEIGHT
from scripts.validate_release_candidate import build_third_rows, norm_county

YEARS = (2014, 2018, 2022)
EVAL_YEARS = (2018, 2022)
SHADOW_HURDLE_ALPHA = 3.0
SHADOW_HURDLE_CLASS_SHRINKAGE = 4.0


def _clean(rows):
    out, seen = [], set()
    for record in rows:
        r = dict(record)
        year, county = int(r['target_year']), norm_county(r['county'])
        key = (year, county)
        if year not in YEARS or key in seen:
            raise ValueError('T3 target-year/county is duplicate or outside audited cycles')
        seen.add(key)
        actual, carry = float(r['target_nonmajor_share']), float(r['previous_nonmajor_share'])
        feature_values = [float(r[f]) for f in T3_FEATURES]
        if not np.isfinite([actual, carry, *feature_values]).all() or not (0 <= actual <= 1 and 0 <= carry <= 1):
            raise ValueError('T3 share or pre-election feature is invalid')
        r['target_year'], r['county'] = year, county
        out.append(r)
    return sorted(out, key=lambda r: (r['target_year'], r['county']))


def _score(rows, field):
    if not rows:
        return {'n': 0, 'mae_pp': None, 'bias_pp': None, 'rmse_pp': None,
                'overestimated': 0, 'over_5pp': 0, 'under_5pp': 0}
    errors = np.asarray([r[field] - r['actual_pct'] for r in rows], dtype=float)
    return {'n': len(rows), 'mae_pp': round(float(np.mean(np.abs(errors))), 4),
            'bias_pp': round(float(np.mean(errors)), 4),
            'rmse_pp': round(float(np.sqrt(np.mean(errors**2))), 4),
            'overestimated': int((errors > 0).sum()), 'over_5pp': int((errors > 5).sum()),
            'under_5pp': int((errors < -5).sum())}


def _paired_bootstrap(rows, left, right, seed=20261102, replicates=2000):
    """County clusters preserve dependence of the same place across cycles."""
    if len(rows) < 2:
        return None
    groups = defaultdict(list)
    for item in rows:
        groups[item['county']].append(item)
    counties = sorted(groups)
    if len(counties) < 2:
        return None
    # Positive = error reduction from using left rather than right.
    per_cluster = [np.asarray(
        [abs(r[right]-r['actual_pct'])-abs(r[left]-r['actual_pct']) for r in groups[c]],
        dtype=float) for c in counties]
    rng = np.random.default_rng(seed)
    estimates = []
    for _ in range(replicates):
        draw = rng.integers(0, len(counties), len(counties))
        parts = [per_cluster[i] for i in draw]
        estimates.append(float(np.concatenate(parts).mean()))
    lo, hi = np.quantile(estimates, [.025, .975])
    return {'cluster_unit': 'county', 'unique_counties': len(counties),
            'replicates': replicates, 'mean_mae_gain_pp': round(float(np.mean(estimates)), 4),
            'ci95_low_pp': round(float(lo), 4), 'ci95_high_pp': round(float(hi), 4),
            'ci_excludes_zero': bool(lo > 0 or hi < 0),
            'ci_positive_gain': bool(lo > 0)}


def build_report_from_rows(source_rows, history_races, *, include_shadow_hurdle=True):
    rows = _clean(source_rows)
    byyear = {yr: [r for r in rows if r['target_year'] == yr] for yr in YEARS}
    if any(not byyear[yr] for yr in YEARS):
        raise ValueError('T3 requires all 2014/2018/2022 audited cycles')
    targets = {(int(r['year']), norm_county(r['county'])): r for r in history_races}
    records, folds = [], []
    for year in EVAL_YEARS:
        train = [r for r in rows if r['target_year'] < year]
        test = byyear[year]
        if not train or max(r['target_year'] for r in train) >= year:
            raise ValueError('T3 chronological training leakage')
        model = fit_t3(train, features=T3_FEATURES, alpha=T3_ALPHA)
        raw = predict_t3(model, test)
        hurdle_model = fit_hurdle(train, features=T3_FEATURES,
                                 alpha=SHADOW_HURDLE_ALPHA,
                                 class_shrinkage=SHADOW_HURDLE_CLASS_SHRINKAGE) if include_shadow_hurdle else None
        alternative = predict_hurdle(hurdle_model, test) if hurdle_model else [None] * len(test)
        for row, raw_value, hurdle_value in zip(test, raw, alternative):
            target = targets.get((year, row['county']))
            if target is None:
                raise ValueError('T3 holdout target missing audited CEC race')
            candidates = target.get('candidates', [])
            major_counts = {party: sum(c.get('party') == party for c in candidates) for party in ('KMT', 'DPP')}
            nonmajor_count = sum(c.get('party') not in ('KMT', 'DPP') for c in candidates)
            raw_share = float(raw_value)
            carry = float(row['previous_nonmajor_share'])
            # Match deployed product: T3 is clipped to zero when there is
            # literally no nonmajor candidate. The T3 model itself is smooth.
            if nonmajor_count:
                estimates = {
                    'carry_pct': 100*carry,
                    't3_raw_pct': 100*raw_share,
                    't3_blend_pct': 100*(T3_MODEL_WEIGHT*raw_share + T3_CARRY_WEIGHT*carry),
                    'hurdle_shadow_pct': 100*float(hurdle_value) if hurdle_value is not None else None,
                }
            else:
                estimates = {
                    'carry_pct': 0.0, 't3_raw_pct': 0.0,
                    't3_blend_pct': 0.0,
                    'hurdle_shadow_pct': 0.0 if hurdle_value is not None else None,
                }
            actual = float(row['target_nonmajor_share'])*100
            if nonmajor_count == 0 and actual > 1.1:
                raise ValueError('T3 historical CEC target contradicts complete candidate roster')
            result = {
                'year': year, 'county': row['county'], 'race_id': row['race_id'],
                'training_years': sorted({int(t['target_year']) for t in train}),
                'actual_pct': round(actual, 4),
                'nonmajor_candidate_count': nonmajor_count,
                'unique_major_pair': major_counts['KMT'] == 1 and major_counts['DPP'] == 1,
                'serious_nonmajor_actual': actual >= 20.0,
                'prior_nonmajor_pct': round(carry*100, 4),
                'no_nonmajor_candidate_forces_zero': nonmajor_count == 0,
                **{k: round(v,4) if v is not None else None for k,v in estimates.items()},
            }
            records.append(result)
        folds.append({
            'target_year':year,
            'training_years':sorted({int(r['target_year']) for r in train}),
            'training_rows':len(train), 'target_rows':len(test),
            'model':'existing_T3_frozen_feature_set',
            'alpha':T3_ALPHA,'blend_t3':T3_MODEL_WEIGHT,'blend_carry':T3_CARRY_WEIGHT,
            'shadow_hurdle_training_rows':len(train) if hurdle_model else 0,
            'retrospective_status':'development_selection_year' if year==2018 else
                'chronological_after_2018_selection_not_pristine_project_holdout',
        })
    cols = ['t3_blend_pct', 't3_raw_pct', 'carry_pct']
    if include_shadow_hurdle:
        cols.append('hurdle_shadow_pct')
    scores = {}
    for year in EVAL_YEARS:
        subset = [r for r in records if r['year'] == year]
        scopes = {
            'all_counties': subset,
            'unique_kmt_dpp_pair': [r for r in subset if r['unique_major_pair']],
            'nonmajor_candidates_present': [r for r in subset if r['nonmajor_candidate_count'] > 0],
            'nonmajor_present_unique_pair': [r for r in subset if r['nonmajor_candidate_count'] > 0 and r['unique_major_pair']],
            'actual_nonmajor_under_20pct': [r for r in subset if r['actual_pct'] < 20],
            'actual_nonmajor_at_least_20pct': [r for r in subset if r['actual_pct'] >= 20],
            'at_least_two_nonmajor_candidates': [r for r in subset if r['nonmajor_candidate_count'] >= 2],
        }
        scores[str(year)] = {
            scope: {'models': {col: _score(group,col) for col in cols},
                    't3_blend_beats_carry_mae': (
                        _score(group,'t3_blend_pct')['mae_pp'] < _score(group,'carry_pct')['mae_pp']
                        if group else None)}
            for scope, group in scopes.items()
        }
    both = [r for r in records if r['nonmajor_candidate_count'] > 0]
    annual = {str(year): _paired_bootstrap(
        [r for r in records if r['year']==year and r['nonmajor_candidate_count'] > 0],
        't3_blend_pct','carry_pct',seed=20261102+year)
        for year in EVAL_YEARS}
    boot = _paired_bootstrap(both,'t3_blend_pct','carry_pct')
    backtest_2022 = scores['2022']['nonmajor_present_unique_pair']
    comparable = backtest_2022['models']
    improvements = [
        scores[str(y)]['nonmajor_candidates_present']['t3_blend_beats_carry_mae']
        for y in EVAL_YEARS
    ]
    return {
        'schema_version':1,
        'kind':'historical_t3_rolling_origin_research_no_2026_forecast_promotion',
        'training_cycles':[2014,2018],
        'evaluation_cycles':[2018,2022],
        'primary_score':'county_equally_weighted_absolute_error_in_non_kmt_dpp_vote_share_pp',
        'third_party_share_denominator':'CEC recorded votes for all listed candidates, not survey responses or undecided voters',
        'model_version':'production_T3_existing_weights_70_30',
        'feature_selection_note':'Current T3 feature set/weights were previously developed using 2018 and later inspected 2022. Folds are time ordered but do not recreate an original untouched holdout.',
        'geography_unit':'county_or_city_election',
        'row_count':len(records),
        'rows_by_year':{str(y):len(byyear[y]) for y in YEARS},
        'excluded_source_rows': len(source_rows)-len(rows),
        'folds':folds, 'scores':scores,
        'bootstrap':{
            'estimator':'paired_carry_minus_t3_absolute_error_pp',
            'cluster_yearly':annual, 'cluster_combined':boot,
            'caution':'2018 and 2022 elections share counties; bootstrap clusters by county, but few cycles limit inference. Do not treat this as unconditioned election-outcome probability calibration.',
        },
        'largest_2022_overestimates': sorted(
            [r for r in records if r['year']==2022],
            key=lambda r: (r['t3_blend_pct']-r['actual_pct']),reverse=True)[:8],
        'largest_2022_underestimates': sorted(
            [r for r in records if r['year']==2022],
            key=lambda r: (r['t3_blend_pct']-r['actual_pct']))[:8],
        'promotion_gate':{
            'diagnostic_all_years_blend_beats_carry_on_present_candidate_races':
                all(v is True for v in improvements),
            '2022_unique_major_pair_present_races':
                comparable['t3_blend_pct']['n'],
            'independent_unseen_future_election_validation':False,
            'end_to_end_probability_calibration':False,
            '2026_forecast_t3_parameters_changed':False,
            'promote_to_formal_forecast':False,
            'status':'blocked_insufficient_independent_cycles',
        },
        'rows': records,
    }


def build_report(root):
    root = Path(root)
    rows, excluded, history = build_third_rows(root)
    report = build_report_from_rows(rows, history)
    report['excluded_source_rows'] = len(excluded)
    report['source_exclusions'] = excluded
    return report


def main():
    root = Path(__file__).resolve().parents[1]
    report = build_report(root)
    print(json.dumps({
        'kind':report['kind'],
        'folds':report['folds'],
        'scores':{year:{
            group:{k:v for k,v in data['models'].items() if k in ('t3_blend_pct','carry_pct','hurdle_shadow_pct')}
            for group,data in metrics.items() if group in ('all_counties','nonmajor_candidates_present','nonmajor_present_unique_pair')
        } for year,metrics in report['scores'].items()},
        'promotion_gate': report['promotion_gate'],
    },ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
