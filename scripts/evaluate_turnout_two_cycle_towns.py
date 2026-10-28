"""Independent district-level 2014→2018 replication of 2018→2022 turnout formulas.

Comparisons are on DIFFERENT matched town cohorts and the same fixed three
formulas. This tests whether 2022 empirical ranking repeats in a different
election cycle; no 2018 outcome used in 2018 predictors, no 2022 outcome used
in 2022 predictors. Does NOT validate 25% old nationwide drift in 2018, as
pre-2014 national trend is unavailable on compatible local-election boundary.
"""
import argparse
import json
import math
import random
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RULES={'persistence':1.,'county_shrink_75':.75,'county_shrink_50':.50}
FIELDS=('electorate','ballots_cast','valid_votes','invalid_votes')


def turnout(v):
    if type(v.get('electorate')) is not int or type(v.get('ballots_cast')) is not int or (
        v['electorate']<=0 or not 0<=v['ballots_cast']<=v['electorate']):
        raise ValueError('Invalid audited township turnout')
    return v['ballots_cast']/v['electorate']


def cycle_score(rows,method):
    weight=sum(x['target_electorate'] for x in rows)
    if not rows or not weight:raise ValueError('No eligible towns')
    return {
        'n_towns':len(rows),
        'electorate_weighted_mae_pp':round(sum(
            x['target_electorate']*abs(x['errors_pp'][method]) for x in rows)/weight,5),
        'electorate_weighted_rmse_pp':round(math.sqrt(sum(
            x['target_electorate']*x['errors_pp'][method]**2 for x in rows)/weight),5),
        'equal_town_mae_pp':round(sum(abs(x['errors_pp'][method]) for x in rows)/len(rows),5)
    }



def county_paired_uncertainty(rows,method,seed=20261028,B=1000):
    """Paired county-cluster uncertainty within a single known election year.

    This is NOT a confidence interval for a new election cycle. It checks
    whether within-cycle MAE gains depend on a few counties.
    """
    if method=='persistence':return None
    by_county={}
    for r in rows:by_county.setdefault(r['county'],[]).append(r)
    names=sorted(by_county)
    if len(names)<3:raise ValueError('Insufficient regional clusters')
    per_county={}
    for name in names:
        group=by_county[name]
        total=sum(x['target_electorate'] for x in group)
        delta=sum(
            x['target_electorate']*(abs(x['errors_pp'][method])-
                abs(x['errors_pp']['persistence']))
            for x in group)/total
        per_county[name]=delta
    rng=random.Random(seed)
    draws=[]
    for _ in range(B):
        sample=[rng.choice(names) for _ in names]
        total=0.;numerator=0.
        for name in sample:
            for r in by_county[name]:
                wt=r['target_electorate']
                total+=wt
                numerator+=wt*(abs(r['errors_pp'][method])-
                    abs(r['errors_pp']['persistence']))
        draws.append(numerator/total)
    draws.sort()
    loo=[]
    for excluded in names:
        rest=[r for r in rows if r['county']!=excluded]
        total=sum(x['target_electorate'] for x in rest)
        difference=sum(x['target_electorate']*(
            abs(x['errors_pp'][method])-abs(x['errors_pp']['persistence']))
            for x in rest)/total
        loo.append({'excluded_county':excluded,'delta_mae_pp':round(difference,5)})
    return {
        'cluster_unit':'county',
        'n_counties':len(names),
        'resamples':B,
        'bootstrap_90pct_delta_mae_vs_persistence_pp':[
            round(draws[int(B*.05)],5),round(draws[int(B*.95)-1],5)],
        'counties_improved':sum(x < -1e-9 for x in per_county.values()),
        'counties_worse':sum(x > 1e-9 for x in per_county.values()),
        'leave_one_county_out':loo,
        'leave_one_county_out_improved_fraction':round(
            sum(x['delta_mae_pp']<0 for x in loo)/len(loo),5),
        'interpretation':'One election-year resampled by counties, not cross-election forecast calibration or a causal confidence interval'
    }


def evaluate(panel14, panel18, history, shadow2022=None):
    if (panel14.get('kind')!='observed_cec_2014_to_2018_town_turnout_holdout_input' or
        not panel14.get('no_cross_year_precinct_join') or
        panel14.get('official_2026_forecast_unchanged') is not True or
        panel18.get('kind')!='observed_turnout_district_panel_not_an_individual_turnout_model' or
        panel18.get('official_forecast_unchanged') is not True):
        raise ValueError('Unverified original CEC administrative join')
    if len(panel14.get('counties',[]))!=22 or len(panel18.get('counties',[]))!=22:
        raise ValueError('Expected 22 counties in each 2-year panel')
    races=history.get('races',[])
    if len(races)!=66:raise ValueError('Expected 66 official county mayor election totals')
    base={(r['year'],r['county']):r for r in races}
    cycles={}
    for old_year,new_year,panel,status in [
        (2014,2018,panel14,'matched_original_code_name'),
        (2018,2022,panel18,'matched_code_name_only')
    ]:
        rows=[]
        count_coverage={}
        for county in panel['counties']:
            if county['status']!=status and not (old_year==2014 and county['status']=='matched_original_code_name_with_documented_2015_renames'):continue
            name=county['county']
            previous=base[(old_year,name)]
            t_county=turnout(previous)
            eligible=0
            for town in county['districts']:
                a=town['years'][str(old_year)]
                b=town['years'][str(new_year)]
                t0,t1=turnout(a),turnout(b)
                if any(type(a.get(f)) is not int or type(b.get(f)) is not int for f in FIELDS):
                    raise ValueError('Missing audited administrative vote accounting')
                if a['valid_votes']+a['invalid_votes']!=a['ballots_cast'] or b['valid_votes']+b['invalid_votes']!=b['ballots_cast']:
                    raise ValueError('Incorrect town valid/invalid vote conservation')
                predictions={key:t_county+w*(t0-t_county) for key,w in RULES.items()}
                rows.append({'county':name,'district':town['district'],
                   'training_year':old_year,'test_year':new_year,
                   'target_electorate':b['electorate'],
                   'input_turnout_pct':round(100*t0,5),
                   'observed_turnout_pct':round(100*t1,5),
                   'forecast_pct':{key:round(100*p,5) for key,p in predictions.items()},
                   'errors_pp':{key:100*(p-t1) for key,p in predictions.items()}})
                eligible+=b['electorate']
            count_coverage[name]={
                'matched_towns':len(county['districts']),
                'target_electorate_covered':eligible,
                'target_county_electorate':base[(new_year,name)]['electorate'],
                'coverage_fraction':round(eligible/base[(new_year,name)]['electorate'],6)}
        expected=panel['matched_towns'] if old_year==2014 else panel['matched_districts']
        if len(rows)!=expected or len(count_coverage)==0:
            raise ValueError('Comparison does not cover verified prior-year paired towns')
        scores={k:cycle_score(rows,k) for k in RULES}
        for k in RULES:
            scores[k]['delta_mae_vs_persistence_pp']=round(
                scores[k]['electorate_weighted_mae_pp']-
                scores['persistence']['electorate_weighted_mae_pp'],5)
        for method in RULES:
            scores[method]['paired_county_uncertainty'] = county_paired_uncertainty(rows,method)
        if new_year==2022 and shadow2022 is not None:
            if shadow2022.get('kind')!='turnout_forecast_shadow_ablation_2022_exploratory' or (
                shadow2022.get('training_cutoff_election')!=2018):
                raise ValueError('Original 2022 model source not eligible')
            for k in RULES:
                previous_score=shadow2022['scores'][k]['mae_pp']
                if abs(previous_score-scores[k]['electorate_weighted_mae_pp'])>0.00016:
                    raise ValueError('Two-cycle shadow cannot reproduce original 2022 model '+k)
        cycles[f'{old_year}_to_{new_year}']={
            'training_election':old_year,'held_out_election':new_year,
            'matched_counties':len(count_coverage),'matched_towns':len(rows),
            'scores':scores,'coverage':count_coverage,'towns':rows
        }
    replicated=[k for k in RULES if k!='persistence' and
        all(c['scores'][k]['delta_mae_vs_persistence_pp']<0 for c in cycles.values())]
    return {
        'schema_version':1,'kind':'cec_two_independent_town_turnout_cycles_2014_2022',
        'source':'CEC original 2014 elbase + archived original elprof 2014/2018/2022',
        'years':[2014,2018,2022],
        'rules':RULES,'cycles':cycles,'no_future_outcome_predictors':True,
        'different_cohorts_do_not_pool':True,
        'same_formula_weights_across_both_cycles':True,
        'uncertainty_method':'For each held-out cycle separately: 1000 paired county-cluster bootstrap replicates plus leave-one-county-out MAE delta vs persistence; this does not establish confidence intervals for future cycles.',
        'candidate_vote_data_used':False,
        'improved_both_cycles':replicated,
        'model_limit':'2014 and 2022 holdouts are retrospective, only two cycles. 2022 model selection already occurred; no validated vote-choice link.',
        'nonreplicable_old_trend_warning':'2022 winning national_drift_25 has no pre-2014 same-boundary national drift input for 2018; it is NOT validated across both cycles.',
        'promotion_gate':{'status':'blocked','formal_hb_tlef_unchanged':True,
            'allow_2026_candidate_win_probability_modification':False},
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--prior',type=Path,default=ROOT/'data/turnout-district-panel-2014-2018.json')
    p.add_argument('--recent',type=Path,default=ROOT/'data/turnout-district-panel-2018-2022.json')
    p.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    p.add_argument('--shadow',type=Path,default=ROOT/'data/turnout-shadow-ablation-2022.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/turnout-two-cycle-town-validation.json')
    args=p.parse_args()
    read=lambda f:json.loads(f.read_text(encoding='utf8'))
    d=evaluate(read(args.prior),read(args.recent),read(args.history),
               read(args.shadow) if args.shadow.is_file() else None)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({
        'cycles':{k:{'matched_counties':v['matched_counties'],
                     'matched_towns':v['matched_towns'],
                     'weighted_MAE_pp':{name:s['electorate_weighted_mae_pp'] for name,s in v['scores'].items()}}
                  for k,v in d['cycles'].items()},
        'improved_both_cycles':d['improved_both_cycles'],
        'promotion':d['promotion_gate']['status']},ensure_ascii=False))

if __name__=='__main__':main()
