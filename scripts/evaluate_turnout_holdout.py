"""Pre-registered time-ordered 2022 turnout baselines and descriptive association.

Train/proxy inputs end in 2018; labels are 2022. Comparisons of realized
2018→2022 turnout changes with candidate share changes are POST-ELECTION
descriptions, never predictive features, causal estimates or party targeting.
"""
import argparse
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def safe_rate(ballots,electorate):
    if not isinstance(ballots,int) or not isinstance(electorate,int) or electorate<=0 or ballots<0 or ballots>electorate:
        raise ValueError('Invalid CEC turnout counts')
    return ballots/electorate

def county_prior(history):
    races={(x['year'],x['county']):x for x in history['races']}
    result={}
    for (_,county) in races:
        if county in result:continue
        a,b=races.get((2014,county)),races.get((2018,county))
        if not a or not b:continue
        p14=safe_rate(a['ballots_cast'],a['electorate'])
        p18=safe_rate(b['ballots_cast'],b['electorate'])
        result[county]=p18-p14
    return result

def aggregate_errors(rows):
    if not rows:return None
    n=len(rows)
    total=sum(x['weight'] for x in rows)
    return {'towns':n,'electorate_weighted_mae_pp':round(
      sum(x['weight']*abs(x['error_pp']) for x in rows)/total,4),
      'electorate_weighted_rmse_pp':round(math.sqrt(
        sum(x['weight']*x['error_pp']**2 for x in rows)/total),4),
      'equal_town_mae_pp':round(sum(abs(x['error_pp']) for x in rows)/n,4)}

def weighted_centered_corr(rows):
    """Within-county centered, electorate weighted *descriptive* correlation."""
    if len(rows)<12 or len({x['county'] for x in rows})<3:return None
    by_county={}
    for row in rows:by_county.setdefault(row['county'],[]).append(row)
    residual=[]
    for county,arr in by_county.items():
        sw=sum(x['weight'] for x in arr)
        mx=sum(x['turnout_change_pp']*x['weight'] for x in arr)/sw
        my=sum(x['party_share_change_pp']*x['weight'] for x in arr)/sw
        residual.extend((x['weight'],x['turnout_change_pp']-mx,
                         x['party_share_change_pp']-my) for x in arr)
    xx=sum(w*x*x for w,x,y in residual)
    yy=sum(w*y*y for w,x,y in residual)
    xy=sum(w*x*y for w,x,y in residual)
    if xx<=0 or yy<=0:return None
    return round(xy/(xx*yy)**.5,5)

def evaluate(turnout_panel,history,association=None):
    if turnout_panel.get('schema_version')!=1 or len(turnout_panel.get('counties',[]))!=22:
        raise ValueError('Unknown turnout panel')
    if len(history.get('races',[]))!=66:raise ValueError('Historical candidate source incomplete')
    priors=county_prior(history)
    if len(priors)!=22:raise ValueError('Historical pre-2018 county priors incomplete')
    county_rows=[]
    pairs=[]
    for county in turnout_panel['counties']:
        name=county['county']
        if county['status']!='matched_code_name_only':continue
        if name not in priors:raise ValueError('No pre-2022 prior')
        for d in county['districts']:
            a,b=d['years']['2018'],d['years']['2022']
            t18=safe_rate(a['ballots_cast'],a['electorate'])
            t22=safe_rate(b['ballots_cast'],b['electorate'])
            predict_persistence=t18
            # This county-level drift is fully measured by late 2018.
            # No 2022 county turnout or candidate votes enter either prediction.
            predict_old_drift=min(.99,max(.01,t18+priors[name]))
            county_rows.append({
                'county':name,'district':d['district'],'code':d['district_code'],
                'actual_2022_pct':round(t22*100,4),
                'historical_2018_pct':round(t18*100,4),
                'training_prior_2014_to_2018_pp':round(100*priors[name],4),
                'predictions':{
                    '2018_persistence_pct':round(100*predict_persistence,4),
                    '2014_to_2018_county_drift_pct':round(100*predict_old_drift,4)},
                'errors_pp':{
                    '2018_persistence':(predict_persistence-t22)*100,
                    '2014_to_2018_county_drift':(predict_old_drift-t22)*100},
                'test_electorate':b['electorate'],
                'timestamp_gate':{
                    'last_predictor_election':2018,
                    'outcome_election':2022,
                    'no_2022_predictor':True}
            })
    if len(county_rows)!=turnout_panel['matched_districts']:
        raise ValueError('Holdout does not cover verified matched districts')
    methods=['2018_persistence','2014_to_2018_county_drift']
    summary={}
    for method in methods:
        errors=[{'weight':r['test_electorate'],'error_pp':r['errors_pp'][method]}
                for r in county_rows]
        summary[method]=aggregate_errors(errors)
    association_summary={'status':'no_audited_elctks_candidate_data','comparable_towns':0,
        'within_county_centered_weighted_pearson':None}
    if association is not None:
        if (association.get('kind')!='historical_ecological_candidate_turnout_association_only' or
           not association.get('official_forecast_unchanged')):
            raise ValueError('Candidate vote source was not audited')
        if association['matched_towns']!=turnout_panel['matched_districts']:
            raise ValueError('Candidate/turnout panel mismatch')
        lookup={(c['county'],d['district_code']):d
           for c in association['counties'] for d in c['districts']}
        for r in county_rows:
            d=lookup.get((r['county'],r['code']))
            if d is None:raise ValueError('Missing paired candidate town')
            if d['party_comparison_eligible']:
                if abs(d['delta_turnout_pp'] - (r['actual_2022_pct']-r['historical_2018_pct']))>.0002:
                    raise ValueError('Candidate and turnout delta diverge')
                pairs.append({'county':r['county'],'district':r['district'],
                              'weight':r['test_electorate'],
                              'turnout_change_pp':d['delta_turnout_pp'],
                              'party_share_change_pp':d['delta_KMT_two_party_share_pp']})
        association_summary={
            'status':'post_election_ecological_descriptive_only',
            'comparable_towns':len(pairs),
            'counties':len({x['county'] for x in pairs}),
            'within_county_centered_weighted_pearson':weighted_centered_corr(pairs),
            'non_inferential':True,
            'no_2026_predictor':'2022 observed turnout changes are outcomes and unavailable before election',
            'covariates_not_controlled':['candidate quality','incumbency','population shifts',
                                       'demographic turnout propensity','county-wide shocks']
        }
    return {
       'schema_version':1,
       'kind':'cec_historical_time_ordered_turnout_holdout',
       'training_information_cutoff_election':2018,
       'held_out_election':2022,
       'no_2022_training_inputs':True,
       'independent_years_in_holdout':1,
       'calibration_claim':False,
       'official_2026_forecast_unchanged':True,
       'coverage':{'districts':len(county_rows),
                   'counties':len({x['county'] for x in county_rows})},
       'turnout_forecast_score':summary,
       'association':association_summary,
       'evidence_limits':'Pre-2022 naive turnout forecasts only; aggregate 2018–2022 candidate association is descriptive, not causal or a prospective election forecast.',
       'holdout_rows':county_rows
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--turnout',type=Path,default=ROOT/'data/turnout-district-panel-2018-2022.json')
    p.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    p.add_argument('--association',type=Path,default=ROOT/'data/cec-town-candidate-association-2018-2022.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/turnout-holdout-2018-2022.json')
    args=p.parse_args()
    panel=json.loads(args.turnout.read_text(encoding='utf8'))
    history=json.loads(args.history.read_text(encoding='utf8'))
    association=json.loads(args.association.read_text(encoding='utf8')) if args.association.is_file() else None
    report=evaluate(panel,history,association)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'coverage':report['coverage'],
        'forecast_scores':report['turnout_forecast_score'],
        'association':report['association']},ensure_ascii=False))
if __name__=='__main__':main()
