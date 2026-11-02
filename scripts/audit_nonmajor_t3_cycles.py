"""Chronological third-party vote-pool audit (research only; no forecast promotion).

2014 is a training period, not a holdout. 2018 is a chronological validation
period that was consulted during historical T3 model specification selection.
2022 is a later-year test of 2014+2018-fitted parameters, but NOT a pristine
project-wide blind holdout: this architecture was iterated after inspecting
historical outcomes. Final known candidate slates are used as conditional
research inputs; they are not certified as pre-nomination information snapshots.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from model.third_party import fit as fit_t3, predict as predict_t3
from model.v4_product import T3_ALPHA, T3_FEATURES, T3_MODEL_WEIGHT, T3_CARRY_WEIGHT
from scripts.validate_release_candidate import build_third_rows, norm_county

EXPECTED_YEARS = (2014, 2018, 2022)
FORECAST_GUARD = 'blocked_no_independent_probability_calibration_or_multi_cycle_confirmation'


def _load(path):
    return json.loads(path.read_text(encoding='utf8'))


def _metrics(items, field):
    values = np.asarray([r[field] for r in items], dtype=float)
    actual = np.asarray([r['actual_pct'] for r in items], dtype=float)
    errors = values - actual
    if not len(values) or not np.isfinite(errors).all():
        return None
    return {
        'n': len(values),
        'mae_pp': round(float(np.mean(np.abs(errors))), 5),
        'rmse_pp': round(float(np.sqrt(np.mean(errors**2))), 5),
        'bias_pp': round(float(np.mean(errors)), 5),
        'overpredict_n': int(np.sum(errors > .0000001)),
        'underpredict_n': int(np.sum(errors < -.0000001)),
        'median_absolute_error_pp': round(float(np.median(np.abs(errors))), 5),
    }


def _bootstrap_mae_delta(items, left, right, *, draws=4000, seed=20261102):
    """County-paired percentile bootstrap; positive => left is worse."""
    if len(items) < 2:
        return None
    l=np.asarray([abs(r[left]-r['actual_pct']) for r in items])
    rr=np.asarray([abs(r[right]-r['actual_pct']) for r in items])
    rng=np.random.default_rng(seed)
    samples=rng.integers(0,len(items),(draws,len(items)))
    deltas=np.mean((l-rr)[samples],axis=1)
    return {
        'estimated_delta_pp':round(float(np.mean(l-rr)),5),
        'percentile_95_low_pp':round(float(np.quantile(deltas,.025)),5),
        'percentile_95_high_pp':round(float(np.quantile(deltas,.975)),5),
        'unit':'county_paired_resample',
        'bootstrap_draws':draws,
        'interpretation':'positive means first method has higher MAE; bootstrap uncertainty, not a pre-registered significance test',
    }


def _groups(rows):
    groups={
        'nonmajor_candidates_0': lambda r:r['nonmajor_candidate_count']==0,
        'nonmajor_candidates_1': lambda r:r['nonmajor_candidate_count']==1,
        'nonmajor_candidates_2plus': lambda r:r['nonmajor_candidate_count']>=2,
        'has_independent': lambda r:r['independent_candidate_count']>=1,
        'has_tpp': lambda r:r['has_tpp_candidate'],
        'no_tpp': lambda r:not r['has_tpp_candidate'],
        'observed_nonmajor_below_5pct': lambda r:r['actual_pct']<5,
        'observed_nonmajor_above_20pct': lambda r:r['actual_pct']>=20,
    }
    out={}
    for name,select in groups.items():
        subset=[r for r in rows if select(r)]
        out[name]={
            'n':len(subset),
            'production_spec_70_30':_metrics(subset,'production_blended_pct'),
            'lagged_carry':_metrics(subset,'lagged_carry_pct'),
        }
    return out


def build_t3_cycle_audit(root:Path):
    rows,excluded,history=build_third_rows(root)
    counts={year:sum(r['target_year']==year for r in rows) for year in EXPECTED_YEARS}
    races={(r['year'],norm_county(r['county'])):r for r in history}
    if set(counts)!={2014,2018,2022} or any(v!=22 for v in counts.values()):
        raise ValueError(f'Unexpected chronological T3 input coverage: {counts}')
    if excluded:
        raise ValueError(f'T3 unverified exclusion would alter historical comparison: {excluded}')

    paths=[root/'data/candidate-history-cec.json',
           root/'data/baseline/processed/earlier-cycle-derived-features.json',
           root/'data/baseline/processed/later-cycle-derived-features-2022.json']
    provenance={p.relative_to(root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    year_results=[]
    for year,training_years,role in (
        (2018,(2014,),'development_cycle_also_used_in_model_selection'),
        (2022,(2014,2018),'chronological_2022_holdout_not_project_blind'),
    ):
        training=[r for r in rows if r['target_year'] in training_years]
        targets=sorted((r for r in rows if r['target_year']==year),key=lambda x:x['county'])
        if not training or not targets or max(r['target_year'] for r in training)>=year:
            raise ValueError('Future-label leakage in T3 train/test split')
        fitted=fit_t3(training,features=T3_FEATURES,alpha=T3_ALPHA)
        if sorted(fitted['training_years'])!=list(training_years):
            raise ValueError('T3 fitted with target election label')
        predicted=predict_t3(fitted,targets)
        observations=[]
        for row,model_output in zip(targets,predicted):
            county=row['county']
            race=races[(year,county)]
            candidates=race['candidates']
            if any(c.get('votes') is None for c in candidates) or not race.get('counts_verified'):
                raise ValueError('Target election CEC candidate votes were not verified')
            nonmajor=[c for c in candidates if c.get('party') not in {'KMT','DPP'}]
            if len(nonmajor)!=round(np.expm1(row['log_nonmajor_candidate_count'])):
                raise ValueError(f'T3 slate feature differs from observed candidate count: {year} {county}')
            actual=100*sum(int(c['votes']) for c in nonmajor)/race['valid_votes']
            if abs(actual/100-row['target_nonmajor_share'])>1e-7:
                raise ValueError(f'CEC nonmajor share differs from model target: {year} {county}')
            # Production T3 composition cannot assign votes to nonexistent minor
            # candidates. This is a structural zero, not outcome-derived clipping.
            prediction=float(model_output) if nonmajor else 0.
            previous=row['previous_nonmajor_share'] if nonmajor else 0.
            blended=T3_MODEL_WEIGHT*prediction+T3_CARRY_WEIGHT*previous
            observations.append({
                'county':county, 'year':year,
                'candidate_count':len(candidates),
                'nonmajor_candidate_count':len(nonmajor),
                'independent_candidate_count':sum(
                    c.get('party') is None or c.get('legacy_bloc')=='IND' for c in nonmajor),
                'has_tpp_candidate':bool(row['has_tpp_candidate']),
                'actual_pct':round(actual,6),
                'production_t3_raw_pct':round(100*prediction,6),
                'production_blended_pct':round(100*blended,6),
                'lagged_carry_pct':round(100*previous,6),
                't3_blended_error_pp':round(100*blended-actual,6),
                'cec_race_id':race['race_id'],
                'source_verified_county_results':race['counts_verified'],
            })
        metric={
            'production_spec_raw':_metrics(observations,'production_t3_raw_pct'),
            'production_spec_70_30':_metrics(observations,'production_blended_pct'),
            'lagged_carry':_metrics(observations,'lagged_carry_pct'),
        }
        year_results.append({
            'year':year,'role':role,'training_years':list(training_years),
            'model_features':list(T3_FEATURES),'model_alpha':T3_ALPHA,
            'blending_weights':{'t3':T3_MODEL_WEIGHT,'previous_election':T3_CARRY_WEIGHT},
            'source_counties':len(observations),
            'metrics':metric,
            'paired_mae_70_30_minus_carry':_bootstrap_mae_delta(
                observations,'production_blended_pct','lagged_carry_pct',seed=20261102+year),
            'groups':_groups(observations),
            'largest_absolute_errors':sorted(
                observations,key=lambda r:abs(r['t3_blended_error_pp']),reverse=True)[:8],
            'county_rows':observations,
        })
    # The 2018 outcome was examined when selecting the T3 feature specification.
    # Do NOT sum 2018+2022 as if these were two untouched confirmation cycles.
    return {
        'schema_version':1,
        'kind':'t3_chronological_nonmajor_mass_bias_audit_not_forecast_calibration',
        'as_of':'2026-11-02',
        'historical_years_available':list(EXPECTED_YEARS),
        'training_year_only':2014,
        'selection_year':2018,
        'chronological_test_year':2022,
        'rows_by_target_year':{str(y):counts[y] for y in EXPECTED_YEARS},
        'primary_source_sha256':provenance,
        'measurement':'actual percentage of valid ballots cast for candidates other than KMT and DPP',
        'target_slate':'archived complete final candidate list; not individually certified as available before nomination',
        'selection_warning':'2018 chosen in historical model development; 2022 chronological test does not mean project-wide pristine holdout',
        'bootstrap_warning':'Only 22 county clusters per year; percentile CIs describe sampling sensitivity and cannot certify probability calibration',
        'metrics_use_observed_year_outcomes':True,
        'forecast_2026_modified':False,
        'probability_calibrated':False,
        'promotion_gate':{
            'status':'blocked',
            'code':FORECAST_GUARD,
            'reason':'Do not change 2026 T3 vote center based on 2018 selection-period results and one previously inspected 2022 election, without truly independent additional cycles and candidate-slate vintage validation',
        },
        'cycles':year_results,
    }


def main():
    root=Path(__file__).resolve().parents[1]
    output=build_t3_cycle_audit(root)
    print(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=='__main__':
    main()
