"""Frozen-formula 2022 turnout shadow ablation, with strict temporal separation.

Inputs: 2014/2018 CEC county turnout and 2018 CEC district turnout.
Outcomes: 2022 CEC district turnout, used ONLY for scoring.
All formula weights are fixed *before this script scores 2022*.
Since the researcher has already seen the 2022 baseline, these are
exploratory retrospective shadow comparisons, not new prospective validation.
No candidate preference, causal effects or 2026 candidate forecast inputs.
"""
import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SHADOWS=(
    ('persistence','2018鄉鎮投票率直接延用'),
    ('county_shrink_75','2018地方偏離縣市均值保留75%'),
    ('county_shrink_50','2018地方偏離縣市均值保留50%'),
    ('county_drift_25','2014—2018縣市舊趨勢的25%'),
    ('national_drift_25','2014—2018全台歷史趨勢的25%'),
    ('shrink_75_drift_25','地方差異保留75%＋舊縣市趨勢25%'),
    ('county_drift_100','2014—2018縣市舊趨勢的100%'),
)
MODEL_RULES={
    'persistence':{'shrink':1.,'drift':0.,'trend':'none'},
    'county_shrink_75':{'shrink':.75,'drift':0.,'trend':'none'},
    'county_shrink_50':{'shrink':.50,'drift':0.,'trend':'none'},
    'county_drift_25':{'shrink':1.,'drift':.25,'trend':'county'},
    'national_drift_25':{'shrink':1.,'drift':.25,'trend':'national'},
    'shrink_75_drift_25':{'shrink':.75,'drift':.25,'trend':'county'},
    'county_drift_100':{'shrink':1.,'drift':1.,'trend':'county'},
}
WEIGHTED_METRIC='2022 electorate-weighted MAE in percentage points'

def rate(c):
    e,v=c['electorate'],c['ballots_cast']
    if not isinstance(e,int) or e<=0 or not isinstance(v,int) or not 0<=v<=e:
        raise ValueError('Invalid official CEC turnout integer counts')
    return v/e

def history_inputs(history):
    if len(history.get('races',[]))!=66:raise ValueError('CEC historical county coverage incomplete')
    pairs={(r['year'],r['county']):r for r in history['races']}
    counties=sorted({c for (y,c) in pairs})
    if len(counties)!=22:raise ValueError('Not 22 county histories')
    lookup={}
    prev_eligible=0
    prev_ballots=0
    newer_eligible=0
    newer_ballots=0
    for county in counties:
        older=pairs[(2014,county)];current=pairs[(2018,county)]
        old_rate=rate(older);now_rate=rate(current)
        lookup[county]={'t14':old_rate,'t18':now_rate,'county_drift':now_rate-old_rate}
        prev_eligible+=older['electorate'];prev_ballots+=older['ballots_cast']
        newer_eligible+=current['electorate'];newer_ballots+=current['ballots_cast']
    return lookup,newer_ballots/newer_eligible-prev_ballots/prev_eligible

def shadow_predictions(t18,county_info,national_drift):
    if not 0<=t18<=1:raise ValueError('Invalid district predictor rate')
    values={}
    for key,rule in MODEL_RULES.items():
        baseline=county_info['t18']+rule['shrink']*(t18-county_info['t18'])
        delta=county_info['county_drift'] if rule['trend']=='county' else (
            national_drift if rule['trend']=='national' else 0.)
        value=baseline+rule['drift']*delta
        values[key]=min(.99,max(.01,value))
    return values

def metrics(rows,key):
    if not rows:return None
    total=sum(x['weight'] for x in rows)
    return {
        'n_towns':len(rows),
        'mae_pp':round(sum(x['weight']*abs(x['errors_pp'][key]) for x in rows)/total,4),
        'rmse_pp':round(math.sqrt(sum(x['weight']*x['errors_pp'][key]**2 for x in rows)/total),4),
        'mean_bias_pp':round(sum(x['weight']*x['errors_pp'][key] for x in rows)/total,4)
    }

def paired_bootstrap_by_county(rows,key,seed=20261028,B=1000):
    groups=defaultdict(list)
    for row in rows:groups[row['county']].append(row)
    names=sorted(groups)
    rng=random.Random(seed)
    res=[]
    for _ in range(B):
        selection=[rng.choice(names) for _ in names]
        total=0.;dif=0.
        for county in selection:
            for row in groups[county]:
                w=row['weight']
                total+=w
                dif+=w*(abs(row['errors_pp'][key])-abs(row['errors_pp']['persistence']))
        res.append(dif/total)
    res.sort()
    return {'difference_vs_persistence_mae_pp_90pct_county_bootstrap':
            [round(res[int(.05*B)],4),round(res[int(.95*B)-1],4)],
            'cluster_unit':'county','n_counties':len(names),
            'uncertainty_warning':'County resampling from ONE held-out election; not a multi-election prospective uncertainty interval.'}

def compare(panel,history,original_holdout=None):
    if panel.get('schema_version')!=1 or panel.get('kind')!='observed_turnout_district_panel_not_an_individual_turnout_model' or not panel.get('official_forecast_unchanged'):
        raise ValueError('Only verified historical district panel allowed')
    if len(panel.get('counties',[]))!=22:raise ValueError('Not all 22 county entries supplied')
    prior,national_drift=history_inputs(history)
    rows=[]
    for county in panel['counties']:
        name=county['county']
        if county['status']!='matched_code_name_only':continue
        info=prior[name]
        for district in county['districts']:
            y=district['years']
            t18=rate(y['2018'])
            truth=rate(y['2022'])
            forecast=shadow_predictions(t18,info,national_drift)
            row={
                'county':name,'district':district['district'],
                'weight':y['2022']['electorate'],
                'historical_2018_turnout_pct':round(t18*100,4),
                'observed_2022_turnout_pct':round(truth*100,4),
                'forecast_pct':{k:round(v*100,4) for k,v in forecast.items()},
                'errors_pp':{k:100*(v-truth) for k,v in forecast.items()}
            }
            rows.append(row)
    if len(rows)!=panel['matched_districts']:
        raise ValueError('Historical evaluation row count does not match verified district panel')
    results={}
    for key,label in SHADOWS:
        stats=metrics(rows,key)
        stats['label']=label
        results[key]=stats
    if original_holdout is not None:
        if (original_holdout.get('kind')!='cec_historical_time_ordered_turnout_holdout' or
            original_holdout.get('held_out_election')!=2022 or
            original_holdout.get('training_information_cutoff_election')!=2018 or
            original_holdout['coverage']['districts']!=len(rows)):
            raise ValueError('Original 2022 holdout cannot be reconciled')
        old=original_holdout['turnout_forecast_score']['2018_persistence']
        current=results['persistence']
        if abs(old['electorate_weighted_mae_pp']-current['mae_pp'])>0.00015 or abs(old['electorate_weighted_rmse_pp']-current['rmse_pp'])>0.00015:
            raise ValueError('Shadow base forecast does not reproduce first audited holdout')
    baseline=results['persistence']
    per_county=[]
    for county in sorted({r['county'] for r in rows}):
        group=[r for r in rows if r['county']==county]
        per_county.append({
            'county':county,'towns':len(group),
            'metrics':{key:metrics(group,key) for key,_ in SHADOWS}
        })
    for key,_ in SHADOWS:
        delta=round(results[key]['mae_pp']-baseline['mae_pp'],4)
        results[key]['delta_mae_vs_persistence_pp']=delta
        if key=='persistence':
            results[key]['county_bootstrap']=None
            continue
        results[key]['county_bootstrap']=paired_bootstrap_by_county(rows,key)
        results[key]['counties_with_lower_mae']=sum(
            c['metrics'][key]['mae_pp'] < c['metrics']['persistence']['mae_pp']-.00005 for c in per_county)
        results[key]['counties_tied']=sum(
            abs(c['metrics'][key]['mae_pp']-c['metrics']['persistence']['mae_pp'])<=.00005 for c in per_county)
    ranked=sorted((key for key,_ in SHADOWS),key=lambda key:results[key]['mae_pp'])
    return {
      'schema_version':1,
      'kind':'turnout_forecast_shadow_ablation_2022_exploratory',
      'training_cutoff_election':2018,
      'holdout_election':2022,
      'coverage':{'counties':len(per_county),'towns':len(rows)},
      'candidate_party_votes_used_in_predictors':False,
      'uses_2022_outcomes_only_for_scoring':True,
      'formula_weights_frozen_at_script_execution':True,
      'exploratory_selection_warning':'Researchers have already inspected the 2022 test set. Comparing these additional formulas on the same set is a RETROSPECTIVE ablation, not new independent holdout validation; do not tune or deploy winning formula to 2026.',
      'formula_spec':MODEL_RULES,
      'national_2014_to_2018_turnout_drift_pp':round(100*national_drift,4),
      'scores':results,
      'best_2022_model_posthoc_only':ranked[0],
      'promotion_gate':{
        'status':'blocked',
        'reason':'Only one held-out cycle, county boundary screen only, no independently replicated performance and no validated participation/candidate-choice joint model.',
        'formal_hb_tlef_unchanged':True,
        'allow_2026_candidate_win_probability_modification':False
      },
      'per_county':per_county,
      'holdout_rows':rows
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--panel',type=Path,default=ROOT/'data/turnout-district-panel-2018-2022.json')
    p.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    p.add_argument('--previous-holdout',type=Path,default=ROOT/'data/turnout-holdout-2018-2022.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/turnout-shadow-ablation-2022.json')
    args=p.parse_args()
    get=lambda file:json.loads(file.read_text(encoding='utf8'))
    d=compare(get(args.panel),get(args.history),get(args.previous_holdout))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'coverage':d['coverage'],'scores':{
        k:{'mae_pp':v['mae_pp'],'delta_vs_base':v['delta_mae_vs_persistence_pp']}
        for k,v in d['scores'].items()},'promote':d['promotion_gate']['status']},ensure_ascii=False))
if __name__=='__main__':main()
